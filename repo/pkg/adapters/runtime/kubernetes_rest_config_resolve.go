package runtime

import (
	"errors"
	"fmt"
	"os"
	"strings"

	"github.com/kubercloud/ani/pkg/ports"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
)

// KubernetesRESTCredentialSource records how Kubernetes REST credentials were resolved.
type KubernetesRESTCredentialSource string

const (
	KubernetesRESTCredentialExplicitEnv KubernetesRESTCredentialSource = "explicit_env"
	KubernetesRESTCredentialKubeconfig  KubernetesRESTCredentialSource = "kubeconfig"
	KubernetesRESTCredentialInCluster   KubernetesRESTCredentialSource = "in_cluster"
)

var errKubernetesRESTCredentialUnavailable = errors.New("kubernetes rest credentials unavailable")

// ResolveKubernetesRESTClientConfig fills missing host/token/TLS settings.
// Priority: explicit config > kubeconfig > in-cluster service account.
func ResolveKubernetesRESTClientConfig(seed KubernetesRESTClientConfig) (KubernetesRESTClientConfig, KubernetesRESTCredentialSource, error) {
	if hasExplicitKubernetesRESTConfig(seed) {
		return seed, KubernetesRESTCredentialExplicitEnv, nil
	}
	if !kubernetesConfigAutoLoadEnabled() {
		return KubernetesRESTClientConfig{}, "", fmt.Errorf(
			"%w: set KUBERNETES_API_HOST/KUBERNETES_BEARER_TOKEN, KUBERNETES_SERVICE_HOST, kubeconfig, or enable in-cluster credentials",
			ports.ErrInvalid,
		)
	}

	kubeconfigPath := strings.TrimSpace(os.Getenv("KUBECONFIG"))
	kubeconfigContext := strings.TrimSpace(os.Getenv("KUBERNETES_CONFIG_CONTEXT"))
	if cfg, err := loadKubernetesRESTFromKubeconfig(kubeconfigPath, kubeconfigContext); err == nil {
		return mergeKubernetesRESTClientConfig(seed, cfg), KubernetesRESTCredentialKubeconfig, nil
	} else if !errors.Is(err, errKubernetesRESTCredentialUnavailable) {
		return KubernetesRESTClientConfig{}, "", err
	}

	if cfg, err := loadKubernetesRESTFromInCluster(seed); err == nil {
		return mergeKubernetesRESTClientConfig(seed, cfg), KubernetesRESTCredentialInCluster, nil
	} else if !errors.Is(err, errKubernetesRESTCredentialUnavailable) {
		return KubernetesRESTClientConfig{}, "", err
	}

	return KubernetesRESTClientConfig{}, "", fmt.Errorf(
		"%w: no Kubernetes credentials found; set KUBERNETES_* env, KUBECONFIG, or run inside a cluster",
		ports.ErrInvalid,
	)
}

func kubernetesConfigAutoLoadEnabled() bool {
	switch strings.ToLower(strings.TrimSpace(os.Getenv("KUBERNETES_CONFIG_AUTO_LOAD"))) {
	case "0", "false", "no", "off":
		return false
	default:
		return true
	}
}

func hasExplicitKubernetesRESTConfig(cfg KubernetesRESTClientConfig) bool {
	if strings.TrimSpace(cfg.Host) != "" {
		return true
	}
	if strings.TrimSpace(cfg.BearerToken) != "" {
		return true
	}
	if strings.TrimSpace(cfg.ServiceHost) != "" {
		return true
	}
	if strings.TrimSpace(cfg.BearerTokenFile) != "" {
		return true
	}
	if strings.TrimSpace(cfg.CAFile) != "" {
		return true
	}
	return cfg.HTTPClient != nil
}

func loadKubernetesRESTFromKubeconfig(kubeconfigPath, contextName string) (KubernetesRESTClientConfig, error) {
	loadingRules := clientcmd.NewDefaultClientConfigLoadingRules()
	if kubeconfigPath != "" {
		loadingRules.ExplicitPath = kubeconfigPath
	}
	overrides := &clientcmd.ConfigOverrides{}
	if contextName != "" {
		overrides.CurrentContext = contextName
	}
	clientConfig := clientcmd.NewNonInteractiveDeferredLoadingClientConfig(loadingRules, overrides)
	if _, err := clientConfig.RawConfig(); err != nil {
		return KubernetesRESTClientConfig{}, fmt.Errorf("%w: %v", errKubernetesRESTCredentialUnavailable, err)
	}
	restConfig, err := clientConfig.ClientConfig()
	if err != nil {
		return KubernetesRESTClientConfig{}, fmt.Errorf("%w: %v", errKubernetesRESTCredentialUnavailable, err)
	}
	httpClient, err := rest.HTTPClientFor(restConfig)
	if err != nil {
		return KubernetesRESTClientConfig{}, err
	}
	cfg := KubernetesRESTClientConfig{
		Host:        strings.TrimRight(strings.TrimSpace(restConfig.Host), "/"),
		BearerToken: strings.TrimSpace(restConfig.BearerToken),
		BearerTokenFile: strings.TrimSpace(restConfig.BearerTokenFile),
		CAFile:          strings.TrimSpace(restConfig.CAFile),
		HTTPClient:      httpClient,
	}
	if cfg.Host == "" {
		return KubernetesRESTClientConfig{}, errKubernetesRESTCredentialUnavailable
	}
	return cfg, nil
}

func loadKubernetesRESTFromInCluster(seed KubernetesRESTClientConfig) (KubernetesRESTClientConfig, error) {
	tokenFile := strings.TrimSpace(seed.BearerTokenFile)
	if tokenFile == "" {
		tokenFile = strings.TrimSpace(os.Getenv("KUBERNETES_SERVICE_ACCOUNT_TOKEN_FILE"))
	}
	if tokenFile == "" {
		tokenFile = defaultKubernetesServiceAccountTokenFile
	}
	if _, err := os.Stat(tokenFile); err != nil {
		return KubernetesRESTClientConfig{}, fmt.Errorf("%w: %v", errKubernetesRESTCredentialUnavailable, err)
	}

	cfg := seed
	if strings.TrimSpace(cfg.ServiceHost) == "" {
		serviceHost := strings.TrimSpace(os.Getenv("KUBERNETES_SERVICE_HOST"))
		if serviceHost == "" {
			serviceHost = "kubernetes.default.svc"
		}
		cfg.ServiceHost = serviceHost
	}
	if strings.TrimSpace(cfg.ServicePort) == "" {
		servicePort := strings.TrimSpace(os.Getenv("KUBERNETES_SERVICE_PORT"))
		if servicePort == "" {
			servicePort = "443"
		}
		cfg.ServicePort = servicePort
	}
	if strings.TrimSpace(cfg.BearerTokenFile) == "" {
		cfg.BearerTokenFile = tokenFile
	}
	if strings.TrimSpace(cfg.CAFile) == "" {
		if caFile := strings.TrimSpace(os.Getenv("KUBERNETES_SERVICE_ACCOUNT_CA_FILE")); caFile != "" {
			cfg.CAFile = caFile
		}
	}
	return cfg, nil
}

func mergeKubernetesRESTClientConfig(seed, resolved KubernetesRESTClientConfig) KubernetesRESTClientConfig {
	if strings.TrimSpace(seed.FieldManager) != "" {
		resolved.FieldManager = seed.FieldManager
	}
	if seed.HTTPClient != nil {
		resolved.HTTPClient = seed.HTTPClient
	}
	if seed.RequestTimeout > 0 {
		resolved.RequestTimeout = seed.RequestTimeout
	}
	if seed.RetryPolicy.MaxAttempts > 0 || seed.RetryPolicy.Timeout > 0 || seed.RetryPolicy.BaseBackoff > 0 {
		resolved.RetryPolicy = seed.RetryPolicy
	}
	if seed.Now != nil {
		resolved.Now = seed.Now
	}
	return resolved
}
