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
	ProviderMode             string
	KubernetesHTTPClient     *http.Client
	KubernetesRequestTimeout time.Duration
}

func gatewaySecretRuntimeConfigFromEnv() gatewaySecretRuntimeConfig {
	return gatewaySecretRuntimeConfig{
		ProviderMode:             os.Getenv("SECRET_PROVIDER_MODE"),
		KubernetesRequestTimeout: gatewayDurationFromEnv("KUBERNETES_REQUEST_TIMEOUT"),
	}
}

func newGatewaySecretService(cfg gatewaySecretRuntimeConfig, metadata ports.MetadataStore) (ports.SecretService, error) {
	options := gatewaySecretServiceOptions(metadata)
	switch strings.TrimSpace(cfg.ProviderMode) {
	case "", "local":
		if len(options) == 0 {
			return nil, nil
		}
		return runtimeadapter.NewLocalSecretService(options...), nil
	case "kubernetes_rest":
		client, err := newGatewayKubernetesRESTClient(cfg.KubernetesHTTPClient, cfg.KubernetesRequestTimeout)
		if err != nil {
			return nil, err
		}
		options = append(options, runtimeadapter.WithSecretProviderApply(runtimeadapter.NewKubernetesSecretProviderAdapter(client)))
		return runtimeadapter.NewLocalSecretService(options...), nil
	default:
		return nil, fmt.Errorf("%w: unsupported SECRET_PROVIDER_MODE %q", ports.ErrUnsupported, cfg.ProviderMode)
	}
}

func gatewaySecretServiceOptions(metadata ports.MetadataStore) []runtimeadapter.SecretServiceOption {
	if metadata == nil {
		return nil
	}
	return []runtimeadapter.SecretServiceOption{
		runtimeadapter.WithSecretResourceStore(runtimeadapter.NewMetadataSecretStore(metadata)),
	}
}
