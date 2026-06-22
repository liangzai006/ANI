package main

import (
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	runtimeadapter "github.com/kubercloud/ani/pkg/adapters/runtime"
	"github.com/kubercloud/ani/pkg/ports"
)

type gatewaySecretRuntimeConfig struct {
	ProviderMode                      string
	KubernetesAPIHost                 string
	KubernetesServiceHost             string
	KubernetesServicePort             string
	KubernetesBearerToken             string
	KubernetesServiceAccountTokenFile string
	KubernetesServiceAccountCAFile    string
	KubernetesProviderManager         string
	HTTPClient                        *http.Client
	KubernetesRequestTimeout          time.Duration
}

func gatewaySecretRuntimeConfigFromEnv() gatewaySecretRuntimeConfig {
	return gatewaySecretRuntimeConfig{
		ProviderMode:                      os.Getenv("SECRET_PROVIDER_MODE"),
		KubernetesAPIHost:                 os.Getenv("KUBERNETES_API_HOST"),
		KubernetesServiceHost:             os.Getenv("KUBERNETES_SERVICE_HOST"),
		KubernetesServicePort:             os.Getenv("KUBERNETES_SERVICE_PORT"),
		KubernetesBearerToken:             os.Getenv("KUBERNETES_BEARER_TOKEN"),
		KubernetesServiceAccountTokenFile: os.Getenv("KUBERNETES_SERVICE_ACCOUNT_TOKEN_FILE"),
		KubernetesServiceAccountCAFile:    os.Getenv("KUBERNETES_SERVICE_ACCOUNT_CA_FILE"),
		KubernetesProviderManager:         os.Getenv("KUBERNETES_PROVIDER_FIELD_MANAGER"),
		KubernetesRequestTimeout:          gatewayDurationFromEnv("KUBERNETES_REQUEST_TIMEOUT"),
	}
}

func newGatewaySecretService(cfg gatewaySecretRuntimeConfig) (ports.SecretService, error) {
	switch strings.TrimSpace(cfg.ProviderMode) {
	case "", "local":
		return nil, nil
	case "kubernetes_rest":
		client, err := runtimeadapter.NewKubernetesRESTClient(runtimeadapter.KubernetesRESTClientConfig{
			Host:            cfg.KubernetesAPIHost,
			ServiceHost:     cfg.KubernetesServiceHost,
			ServicePort:     cfg.KubernetesServicePort,
			BearerToken:     cfg.KubernetesBearerToken,
			BearerTokenFile: cfg.KubernetesServiceAccountTokenFile,
			CAFile:          cfg.KubernetesServiceAccountCAFile,
			FieldManager:    cfg.KubernetesProviderManager,
			HTTPClient:      cfg.HTTPClient,
			RequestTimeout:  cfg.KubernetesRequestTimeout,
		})
		if err != nil {
			return nil, err
		}
		return runtimeadapter.NewLocalSecretService(
			runtimeadapter.WithSecretProviderApply(runtimeadapter.NewKubernetesSecretProviderAdapter(client)),
		), nil
	default:
		return nil, fmt.Errorf("%w: unsupported SECRET_PROVIDER_MODE %q", ports.ErrUnsupported, cfg.ProviderMode)
	}
}
