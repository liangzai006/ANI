package main

import (
	"fmt"
	"net/http"
	"os"
	"strings"

	runtimeadapter "github.com/kubercloud/ani/pkg/adapters/runtime"
	"github.com/kubercloud/ani/pkg/ports"
)

type gatewayGPUInventoryRuntimeConfig struct {
	ProviderMode              string
	KubernetesAPIHost         string
	KubernetesBearerToken     string
	KubernetesProviderManager string
	KubernetesHTTPClient      *http.Client
}

func gatewayGPUInventoryRuntimeConfigFromEnv() gatewayGPUInventoryRuntimeConfig {
	return gatewayGPUInventoryRuntimeConfig{
		ProviderMode:              os.Getenv("GPU_INVENTORY_PROVIDER"),
		KubernetesAPIHost:         os.Getenv("KUBERNETES_API_HOST"),
		KubernetesBearerToken:     os.Getenv("KUBERNETES_BEARER_TOKEN"),
		KubernetesProviderManager: os.Getenv("KUBERNETES_PROVIDER_FIELD_MANAGER"),
	}
}

func newGatewayGPUInventory(cfg gatewayGPUInventoryRuntimeConfig) (ports.GPUInventory, error) {
	switch mode := strings.TrimSpace(cfg.ProviderMode); mode {
	case "", "local", "not_configured":
		return nil, nil
	case "kubernetes_rest":
		client, err := runtimeadapter.NewKubernetesRESTClient(runtimeadapter.KubernetesRESTClientConfig{
			Host:         cfg.KubernetesAPIHost,
			BearerToken:  cfg.KubernetesBearerToken,
			FieldManager: cfg.KubernetesProviderManager,
			HTTPClient:   cfg.KubernetesHTTPClient,
		})
		if err != nil {
			return nil, err
		}
		return runtimeadapter.NewKubernetesGPUInventory(client), nil
	default:
		return nil, fmt.Errorf("%w: unsupported GPU_INVENTORY_PROVIDER %q", ports.ErrUnsupported, mode)
	}
}
