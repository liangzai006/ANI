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

type gatewayNetworkRuntimeConfig struct {
	ProviderMode                      string
	ProviderApply                     bool
	ProviderUserID                    string
	ProviderProof                     string
	KubernetesAPIHost                 string
	KubernetesServiceHost             string
	KubernetesServicePort             string
	KubernetesBearerToken             string
	KubernetesServiceAccountTokenFile string
	KubernetesServiceAccountCAFile    string
	KubernetesProviderManager         string
	KubernetesHTTPClient              *http.Client
	KubernetesRequestTimeout          time.Duration
}

func gatewayNetworkRuntimeConfigFromEnv() gatewayNetworkRuntimeConfig {
	return gatewayNetworkRuntimeConfig{
		ProviderMode:                      os.Getenv("NETWORK_PROVIDER"),
		ProviderApply:                     strings.EqualFold(strings.TrimSpace(os.Getenv("NETWORK_PROVIDER_APPLY_ENABLED")), "true"),
		ProviderUserID:                    os.Getenv("NETWORK_PROVIDER_USER_ID"),
		ProviderProof:                     os.Getenv("NETWORK_PROVIDER_PERMISSION_PROOF"),
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

func newGatewayNetworkService(cfg gatewayNetworkRuntimeConfig) (ports.NetworkService, error) {
	switch mode := strings.TrimSpace(cfg.ProviderMode); mode {
	case "", "local", "not_configured":
		return nil, nil
	case "kubeovn_rest":
		if strings.TrimSpace(cfg.ProviderUserID) == "" || strings.TrimSpace(cfg.ProviderProof) == "" {
			return nil, fmt.Errorf("%w: network provider requires NETWORK_PROVIDER_USER_ID and NETWORK_PROVIDER_PERMISSION_PROOF", ports.ErrInvalid)
		}
		client, err := runtimeadapter.NewKubernetesRESTClient(runtimeadapter.KubernetesRESTClientConfig{
			Host:            cfg.KubernetesAPIHost,
			ServiceHost:     cfg.KubernetesServiceHost,
			ServicePort:     cfg.KubernetesServicePort,
			BearerToken:     cfg.KubernetesBearerToken,
			BearerTokenFile: cfg.KubernetesServiceAccountTokenFile,
			CAFile:          cfg.KubernetesServiceAccountCAFile,
			FieldManager:    cfg.KubernetesProviderManager,
			HTTPClient:      cfg.KubernetesHTTPClient,
			RequestTimeout:  cfg.KubernetesRequestTimeout,
		})
		if err != nil {
			return nil, err
		}
		provider := runtimeadapter.NewKubeOVNNetworkProviderAdapter(
			client,
			runtimeadapter.WithKubeOVNNetworkProviderApplyEnabled(cfg.ProviderApply),
		)
		return runtimeadapter.NewLocalNetworkService(
			runtimeadapter.WithNetworkRouteProvider(
				runtimeadapter.NewKubeOVNNetworkRenderer(),
				provider,
				provider,
				provider,
				runtimeadapter.NetworkProviderExecutionConfig{
					UserID:          cfg.ProviderUserID,
					PermissionProof: cfg.ProviderProof,
				},
			),
		), nil
	default:
		return nil, fmt.Errorf("%w: unsupported NETWORK_PROVIDER %q", ports.ErrUnsupported, mode)
	}
}
