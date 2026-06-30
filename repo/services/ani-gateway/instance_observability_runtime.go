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
	Provider      string
	PrometheusURL string
	ExecBaseURL   string
	HTTPClient    *http.Client
}

func gatewayInstanceObservabilityRuntimeConfigFromEnv() gatewayInstanceObservabilityRuntimeConfig {
	return gatewayInstanceObservabilityRuntimeConfig{
		Provider:      os.Getenv("INSTANCE_OBSERVABILITY_PROVIDER"),
		PrometheusURL: os.Getenv("INSTANCE_OBSERVABILITY_PROMETHEUS_URL"),
		ExecBaseURL:   os.Getenv("INSTANCE_OBSERVABILITY_EXEC_BASE_URL"),
	}
}

func newGatewayInstanceObservability(cfg gatewayInstanceObservabilityRuntimeConfig) (ports.InstanceObservability, bool, error) {
	switch provider := strings.TrimSpace(cfg.Provider); provider {
	case "", "local", "not_configured":
		return nil, false, nil
	case "prometheus_kubernetes":
		k8s := gatewayKubernetesRESTClientConfig(cfg.HTTPClient, 0)
		observability, err := runtimeadapter.NewPrometheusInstanceObservability(runtimeadapter.PrometheusInstanceObservabilityConfig{
			PrometheusURL:                     cfg.PrometheusURL,
			KubernetesAPIHost:                 k8s.Host,
			KubernetesServiceHost:             k8s.ServiceHost,
			KubernetesServicePort:             k8s.ServicePort,
			KubernetesBearerToken:             k8s.BearerToken,
			KubernetesServiceAccountTokenFile: k8s.BearerTokenFile,
			KubernetesServiceAccountCAFile:    k8s.CAFile,
			KubernetesFieldManager:            k8s.FieldManager,
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
