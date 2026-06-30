package main

import (
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/kubercloud/ani/pkg/adapters/objectstore"
	runtimeadapter "github.com/kubercloud/ani/pkg/adapters/runtime"
	"github.com/kubercloud/ani/pkg/ports"
)

type gatewayStorageRuntimeConfig struct {
	ProviderMode               string
	ProviderApply              bool
	ProviderUserID             string
	ProviderProof              string
	KubernetesHTTPClient       *http.Client
	KubernetesRequestTimeout   time.Duration
	ObjectStoreProvider        string
	ObjectStoreEndpoint        string
	ObjectStoreEndpoints       []string
	ObjectStorePublicEndpoint  string
	ObjectStoreAccessKeyID     string
	ObjectStoreSecretAccessKey string
	ObjectStoreSessionToken    string
	ObjectStoreRegion          string
	ObjectStoreSecure          bool
	ObjectStoreBucketPrefix    string
	ObjectStoreHTTPClient      *http.Client
	ObjectStoreRequestTimeout  time.Duration
}

func gatewayStorageRuntimeConfigFromEnv() gatewayStorageRuntimeConfig {
	return gatewayStorageRuntimeConfig{
		ProviderMode:               os.Getenv("STORAGE_PROVIDER"),
		ProviderApply:              strings.EqualFold(strings.TrimSpace(os.Getenv("STORAGE_PROVIDER_APPLY_ENABLED")), "true"),
		ProviderUserID:             os.Getenv("STORAGE_PROVIDER_USER_ID"),
		ProviderProof:              os.Getenv("STORAGE_PROVIDER_PERMISSION_PROOF"),
		KubernetesRequestTimeout:   gatewayDurationFromEnv("KUBERNETES_REQUEST_TIMEOUT"),
		ObjectStoreProvider:        os.Getenv("OBJECT_STORE_PROVIDER"),
		ObjectStoreEndpoint:        os.Getenv("OBJECT_STORE_ENDPOINT"),
		ObjectStoreEndpoints:       splitGatewayCSVEnv(os.Getenv("OBJECT_STORE_ENDPOINTS")),
		ObjectStorePublicEndpoint:  os.Getenv("OBJECT_STORE_PUBLIC_ENDPOINT"),
		ObjectStoreAccessKeyID:     os.Getenv("OBJECT_STORE_ACCESS_KEY_ID"),
		ObjectStoreSecretAccessKey: os.Getenv("OBJECT_STORE_SECRET_ACCESS_KEY"),
		ObjectStoreSessionToken:    os.Getenv("OBJECT_STORE_SESSION_TOKEN"),
		ObjectStoreRegion:          os.Getenv("OBJECT_STORE_REGION"),
		ObjectStoreSecure:          strings.EqualFold(strings.TrimSpace(os.Getenv("OBJECT_STORE_SECURE")), "true"),
		ObjectStoreBucketPrefix:    os.Getenv("OBJECT_STORE_BUCKET_PREFIX"),
		ObjectStoreRequestTimeout:  gatewayDurationFromEnv("OBJECT_STORE_REQUEST_TIMEOUT"),
	}
}

func newGatewayStorageService(cfg gatewayStorageRuntimeConfig, metadata ports.MetadataStore) (ports.StorageService, error) {
	options := gatewayStorageServiceOptions(metadata)
	if strings.TrimSpace(cfg.ObjectStoreProvider) == "minio" {
		store, err := objectstore.NewMinIOObjectStore(objectstore.MinIOObjectStoreConfig{
			Endpoint:        cfg.ObjectStoreEndpoint,
			Endpoints:       cfg.ObjectStoreEndpoints,
			PublicEndpoint:  cfg.ObjectStorePublicEndpoint,
			AccessKeyID:     cfg.ObjectStoreAccessKeyID,
			SecretAccessKey: cfg.ObjectStoreSecretAccessKey,
			SessionToken:    cfg.ObjectStoreSessionToken,
			Region:          cfg.ObjectStoreRegion,
			Secure:          cfg.ObjectStoreSecure,
			BucketPrefix:    cfg.ObjectStoreBucketPrefix,
			HTTPClient:      cfg.ObjectStoreHTTPClient,
			RequestTimeout:  cfg.ObjectStoreRequestTimeout,
		})
		if err != nil {
			return nil, err
		}
		options = append(options, runtimeadapter.WithStorageObjectStore(store))
	}

	switch mode := strings.TrimSpace(cfg.ProviderMode); mode {
	case "", "local", "not_configured":
		if len(options) == 0 {
			return nil, nil
		}
		return runtimeadapter.NewLocalStorageService(options...), nil
	case "kubernetes_rest":
		if strings.TrimSpace(cfg.ProviderUserID) == "" || strings.TrimSpace(cfg.ProviderProof) == "" {
			return nil, fmt.Errorf("%w: storage provider requires STORAGE_PROVIDER_USER_ID and STORAGE_PROVIDER_PERMISSION_PROOF", ports.ErrInvalid)
		}
		client, err := newGatewayKubernetesRESTClient(cfg.KubernetesHTTPClient, cfg.KubernetesRequestTimeout)
		if err != nil {
			return nil, err
		}
		provider := runtimeadapter.NewKubernetesStorageProviderAdapter(
			client,
			runtimeadapter.WithKubernetesStorageProviderApplyEnabled(cfg.ProviderApply),
		)
		options = append(options,
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
		)
		return runtimeadapter.NewLocalStorageService(options...), nil
	default:
		return nil, fmt.Errorf("%w: unsupported STORAGE_PROVIDER %q", ports.ErrUnsupported, mode)
	}
}

func gatewayStorageServiceOptions(metadata ports.MetadataStore) []runtimeadapter.StorageServiceOption {
	if metadata == nil {
		return nil
	}
	return []runtimeadapter.StorageServiceOption{
		runtimeadapter.WithStorageResourceStore(runtimeadapter.NewMetadataStorageStore(metadata)),
	}
}
