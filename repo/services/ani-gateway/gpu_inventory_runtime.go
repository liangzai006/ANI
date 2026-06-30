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

type gatewayGPUInventoryRuntimeConfig struct {
	ProviderMode             string
	KubernetesHTTPClient     *http.Client
	KubernetesRequestTimeout time.Duration
}

func gatewayGPUInventoryRuntimeConfigFromEnv() gatewayGPUInventoryRuntimeConfig {
	return gatewayGPUInventoryRuntimeConfig{
		ProviderMode:             os.Getenv("GPU_INVENTORY_PROVIDER"),
		KubernetesRequestTimeout: gatewayDurationFromEnv("KUBERNETES_REQUEST_TIMEOUT"),
	}
}

func newGatewayGPUInventory(cfg gatewayGPUInventoryRuntimeConfig) (ports.GPUInventory, error) {
	switch mode := strings.TrimSpace(cfg.ProviderMode); mode {
	case "", "local", "not_configured":
		return nil, nil
	case "kubernetes_rest":
		client, err := newGatewayKubernetesRESTClient(cfg.KubernetesHTTPClient, cfg.KubernetesRequestTimeout)
		if err != nil {
			return nil, err
		}
		return runtimeadapter.NewKubernetesGPUInventory(client), nil
	default:
		return nil, fmt.Errorf("%w: unsupported GPU_INVENTORY_PROVIDER %q", ports.ErrUnsupported, mode)
	}
}
