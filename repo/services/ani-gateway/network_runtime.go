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
	ProviderMode             string
	ProviderApply            bool
	ProviderUserID           string
	ProviderProof            string
	KubernetesHTTPClient     *http.Client
	KubernetesRequestTimeout time.Duration
}

func gatewayNetworkRuntimeConfigFromEnv() gatewayNetworkRuntimeConfig {
	return gatewayNetworkRuntimeConfig{
		ProviderMode:             os.Getenv("NETWORK_PROVIDER"),
		ProviderApply:            strings.EqualFold(strings.TrimSpace(os.Getenv("NETWORK_PROVIDER_APPLY_ENABLED")), "true"),
		ProviderUserID:           os.Getenv("NETWORK_PROVIDER_USER_ID"),
		ProviderProof:            os.Getenv("NETWORK_PROVIDER_PERMISSION_PROOF"),
		KubernetesRequestTimeout: gatewayDurationFromEnv("KUBERNETES_REQUEST_TIMEOUT"),
	}
}

func newGatewayNetworkService(cfg gatewayNetworkRuntimeConfig, metadata ports.MetadataStore) (ports.NetworkService, error) {
	baseOptions := gatewayNetworkServiceOptions(metadata)
	switch mode := strings.TrimSpace(cfg.ProviderMode); mode {
	case "", "local", "not_configured":
		if len(baseOptions) == 0 {
			return nil, nil
		}
		return runtimeadapter.NewLocalNetworkService(baseOptions...), nil
	case "kubeovn_rest":
		if strings.TrimSpace(cfg.ProviderUserID) == "" || strings.TrimSpace(cfg.ProviderProof) == "" {
			return nil, fmt.Errorf("%w: network provider requires NETWORK_PROVIDER_USER_ID and NETWORK_PROVIDER_PERMISSION_PROOF", ports.ErrInvalid)
		}
		client, err := newGatewayKubernetesRESTClient(cfg.KubernetesHTTPClient, cfg.KubernetesRequestTimeout)
		if err != nil {
			return nil, err
		}
		provider := runtimeadapter.NewKubeOVNNetworkProviderAdapter(
			client,
			runtimeadapter.WithKubeOVNNetworkProviderApplyEnabled(cfg.ProviderApply),
		)
		options := append(baseOptions,
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
		)
		return runtimeadapter.NewLocalNetworkService(options...), nil
	default:
		return nil, fmt.Errorf("%w: unsupported NETWORK_PROVIDER %q", ports.ErrUnsupported, mode)
	}
}

func gatewayNetworkServiceOptions(metadata ports.MetadataStore) []runtimeadapter.NetworkServiceOption {
	if metadata == nil {
		return nil
	}
	return []runtimeadapter.NetworkServiceOption{
		runtimeadapter.WithNetworkResourceStore(runtimeadapter.NewMetadataNetworkStore(metadata)),
	}
}
