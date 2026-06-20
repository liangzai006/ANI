package main

import (
	"fmt"
	"net/http"
	"os"
	"strings"

	runtimeadapter "github.com/kubercloud/ani/pkg/adapters/runtime"
	"github.com/kubercloud/ani/pkg/ports"
)

type gatewayInstanceObservabilityRuntimeConfig struct {
	Provider                          string
	PrometheusURL                     string
	ExecBaseURL                       string
	KubernetesAPIHost                 string
	KubernetesServiceHost             string
	KubernetesServicePort             string
	KubernetesBearerToken             string
	KubernetesServiceAccountTokenFile string
	KubernetesServiceAccountCAFile    string
	KubernetesFieldManager            string
	HTTPClient                        *http.Client
}

func gatewayInstanceObservabilityRuntimeConfigFromEnv() gatewayInstanceObservabilityRuntimeConfig {
	return gatewayInstanceObservabilityRuntimeConfig{
		Provider:                          os.Getenv("INSTANCE_OBSERVABILITY_PROVIDER"),
		PrometheusURL:                     os.Getenv("INSTANCE_OBSERVABILITY_PROMETHEUS_URL"),
		ExecBaseURL:                       os.Getenv("INSTANCE_OBSERVABILITY_EXEC_BASE_URL"),
		KubernetesAPIHost:                 os.Getenv("KUBERNETES_API_HOST"),
		KubernetesServiceHost:             os.Getenv("KUBERNETES_SERVICE_HOST"),
		KubernetesServicePort:             os.Getenv("KUBERNETES_SERVICE_PORT"),
		KubernetesBearerToken:             os.Getenv("KUBERNETES_BEARER_TOKEN"),
		KubernetesServiceAccountTokenFile: os.Getenv("KUBERNETES_SERVICE_ACCOUNT_TOKEN_FILE"),
		KubernetesServiceAccountCAFile:    os.Getenv("KUBERNETES_SERVICE_ACCOUNT_CA_FILE"),
		KubernetesFieldManager:            os.Getenv("KUBERNETES_PROVIDER_FIELD_MANAGER"),
	}
}

func newGatewayInstanceObservability(cfg gatewayInstanceObservabilityRuntimeConfig) (ports.InstanceObservability, bool, error) {
	switch provider := strings.TrimSpace(cfg.Provider); provider {
	case "", "local", "not_configured":
		return nil, false, nil
	case "prometheus_kubernetes":
		observability, err := runtimeadapter.NewPrometheusInstanceObservability(runtimeadapter.PrometheusInstanceObservabilityConfig{
			PrometheusURL:                     cfg.PrometheusURL,
			KubernetesAPIHost:                 cfg.KubernetesAPIHost,
			KubernetesServiceHost:             cfg.KubernetesServiceHost,
			KubernetesServicePort:             cfg.KubernetesServicePort,
			KubernetesBearerToken:             cfg.KubernetesBearerToken,
			KubernetesServiceAccountTokenFile: cfg.KubernetesServiceAccountTokenFile,
			KubernetesServiceAccountCAFile:    cfg.KubernetesServiceAccountCAFile,
			KubernetesFieldManager:            cfg.KubernetesFieldManager,
			ExecBaseURL:                       cfg.ExecBaseURL,
			HTTPClient:                        cfg.HTTPClient,
		})
		if err != nil {
			return nil, false, err
		}
		return observability, true, nil
	default:
		return nil, false, fmt.Errorf("%w: unsupported INSTANCE_OBSERVABILITY_PROVIDER %q", ports.ErrUnsupported, provider)
	}
}
