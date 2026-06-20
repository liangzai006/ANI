package main

import (
	"fmt"
	"net/http"
	"os"
	"strings"

	runtimeadapter "github.com/kubercloud/ani/pkg/adapters/runtime"
	"github.com/kubercloud/ani/pkg/ports"
)

type gatewayStorageRuntimeConfig struct {
	ProviderMode              string
	ProviderApply             bool
	ProviderUserID            string
	ProviderProof             string
	KubernetesAPIHost         string
	KubernetesBearerToken     string
	KubernetesProviderManager string
	KubernetesHTTPClient      *http.Client
}

func gatewayStorageRuntimeConfigFromEnv() gatewayStorageRuntimeConfig {
	return gatewayStorageRuntimeConfig{
		ProviderMode:              os.Getenv("STORAGE_PROVIDER"),
		ProviderApply:             strings.EqualFold(strings.TrimSpace(os.Getenv("STORAGE_PROVIDER_APPLY_ENABLED")), "true"),
		ProviderUserID:            os.Getenv("STORAGE_PROVIDER_USER_ID"),
		ProviderProof:             os.Getenv("STORAGE_PROVIDER_PERMISSION_PROOF"),
		KubernetesAPIHost:         os.Getenv("KUBERNETES_API_HOST"),
		KubernetesBearerToken:     os.Getenv("KUBERNETES_BEARER_TOKEN"),
		KubernetesProviderManager: os.Getenv("KUBERNETES_PROVIDER_FIELD_MANAGER"),
	}
}

func newGatewayStorageService(cfg gatewayStorageRuntimeConfig) (ports.StorageService, error) {
	switch mode := strings.TrimSpace(cfg.ProviderMode); mode {
	case "", "local", "not_configured":
		return nil, nil
	case "kubernetes_rest":
		if strings.TrimSpace(cfg.ProviderUserID) == "" || strings.TrimSpace(cfg.ProviderProof) == "" {
			return nil, fmt.Errorf("%w: storage provider requires STORAGE_PROVIDER_USER_ID and STORAGE_PROVIDER_PERMISSION_PROOF", ports.ErrInvalid)
		}
		client, err := runtimeadapter.NewKubernetesRESTClient(runtimeadapter.KubernetesRESTClientConfig{
			Host:         cfg.KubernetesAPIHost,
			BearerToken:  cfg.KubernetesBearerToken,
			FieldManager: cfg.KubernetesProviderManager,
			HTTPClient:   cfg.KubernetesHTTPClient,
		})
		if err != nil {
			return nil, err
		}
		provider := runtimeadapter.NewKubernetesStorageProviderAdapter(
			client,
			runtimeadapter.WithKubernetesStorageProviderApplyEnabled(cfg.ProviderApply),
		)
		return runtimeadapter.NewLocalStorageService(
			runtimeadapter.WithStorageProvider(
				runtimeadapter.NewKubernetesStorageRenderer(),
				provider,
				provider,
				provider,
				runtimeadapter.StorageProviderExecutionConfig{
					UserID:          cfg.ProviderUserID,
					PermissionProof: cfg.ProviderProof,
				},
			),
		), nil
	default:
		return nil, fmt.Errorf("%w: unsupported STORAGE_PROVIDER %q", ports.ErrUnsupported, mode)
	}
}
