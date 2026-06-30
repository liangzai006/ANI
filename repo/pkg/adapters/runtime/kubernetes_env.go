package runtime

import (
	"os"
	"strings"
	"time"
)

// KubernetesRESTEnv captures Kubernetes API connection settings from process env.
type KubernetesRESTEnv struct {
	APIHost                 string
	ServiceHost             string
	ServicePort             string
	BearerToken             string
	ServiceAccountTokenFile string
	ServiceAccountCAFile    string
	ProviderFieldManager    string
	KubeconfigPath          string
	KubeconfigContext       string
	RequestTimeout          time.Duration
}

// LoadKubernetesRESTEnvFromOS reads standard KUBERNETES_* variables.
func LoadKubernetesRESTEnvFromOS() KubernetesRESTEnv {
	timeout := time.Duration(0)
	if raw := strings.TrimSpace(os.Getenv("KUBERNETES_REQUEST_TIMEOUT")); raw != "" {
		if parsed, err := time.ParseDuration(raw); err == nil && parsed > 0 {
			timeout = parsed
		}
	}
	return KubernetesRESTEnv{
		APIHost:                 strings.TrimSpace(os.Getenv("KUBERNETES_API_HOST")),
		ServiceHost:             strings.TrimSpace(os.Getenv("KUBERNETES_SERVICE_HOST")),
		ServicePort:             strings.TrimSpace(os.Getenv("KUBERNETES_SERVICE_PORT")),
		BearerToken:             strings.TrimSpace(os.Getenv("KUBERNETES_BEARER_TOKEN")),
		ServiceAccountTokenFile: strings.TrimSpace(os.Getenv("KUBERNETES_SERVICE_ACCOUNT_TOKEN_FILE")),
		ServiceAccountCAFile:    strings.TrimSpace(os.Getenv("KUBERNETES_SERVICE_ACCOUNT_CA_FILE")),
		ProviderFieldManager:    strings.TrimSpace(os.Getenv("KUBERNETES_PROVIDER_FIELD_MANAGER")),
		KubeconfigPath:          strings.TrimSpace(os.Getenv("KUBECONFIG")),
		KubeconfigContext:       strings.TrimSpace(os.Getenv("KUBERNETES_CONFIG_CONTEXT")),
		RequestTimeout:          timeout,
	}
}

// ClientConfig maps env fields into KubernetesRESTClientConfig without credential auto-resolve.
func (e KubernetesRESTEnv) ClientConfig() KubernetesRESTClientConfig {
	return KubernetesRESTClientConfig{
		Host:            e.APIHost,
		ServiceHost:     e.ServiceHost,
		ServicePort:     e.ServicePort,
		BearerToken:     e.BearerToken,
		BearerTokenFile: e.ServiceAccountTokenFile,
		CAFile:          e.ServiceAccountCAFile,
		FieldManager:    e.ProviderFieldManager,
		RequestTimeout:  e.RequestTimeout,
	}
}
