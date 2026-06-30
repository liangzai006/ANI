package main

import (
	"fmt"
	"net/http"
	"os"
	"strings"

	runtimeadapter "github.com/kubercloud/ani/pkg/adapters/runtime"
	"github.com/kubercloud/ani/pkg/ports"
)

type gatewayEncryptionRuntimeConfig struct {
	ProviderMode   string
	KMSBaseURL     string
	KMSBearerToken string
	KMSProvider    string
	HTTPClient     *http.Client
}

func gatewayEncryptionRuntimeConfigFromEnv() gatewayEncryptionRuntimeConfig {
	return gatewayEncryptionRuntimeConfig{
		ProviderMode:   os.Getenv("ENCRYPTION_PROVIDER_MODE"),
		KMSBaseURL:     os.Getenv("KMS_PROVIDER_BASE_URL"),
		KMSBearerToken: os.Getenv("KMS_PROVIDER_BEARER_TOKEN"),
		KMSProvider:    os.Getenv("KMS_PROVIDER_NAME"),
	}
}

func newGatewayEncryptionService(cfg gatewayEncryptionRuntimeConfig, metadata ports.MetadataStore) (ports.EncryptionService, error) {
	options := gatewayEncryptionServiceOptions(metadata)
	switch strings.TrimSpace(cfg.ProviderMode) {
	case "", "local":
		if len(options) == 0 {
			return nil, nil
		}
		return runtimeadapter.NewLocalEncryptionService(options...), nil
	case "kms_sm4_http":
		provider, err := runtimeadapter.NewKMSSM4HTTPEncryptionProvider(runtimeadapter.KMSEncryptionProviderConfig{
			BaseURL:     cfg.KMSBaseURL,
			BearerToken: cfg.KMSBearerToken,
			Provider:    cfg.KMSProvider,
			HTTPClient:  cfg.HTTPClient,
		})
		if err != nil {
			return nil, err
		}
		options = append(options, runtimeadapter.WithEncryptionProvider(provider))
		return runtimeadapter.NewLocalEncryptionService(options...), nil
	default:
		return nil, fmt.Errorf("%w: unsupported ENCRYPTION_PROVIDER_MODE %q", ports.ErrUnsupported, cfg.ProviderMode)
	}
}

func gatewayEncryptionServiceOptions(metadata ports.MetadataStore) []runtimeadapter.EncryptionServiceOption {
	if metadata == nil {
		return nil
	}
	return []runtimeadapter.EncryptionServiceOption{
		runtimeadapter.WithEncryptionResourceStore(runtimeadapter.NewMetadataEncryptionKeyStore(metadata)),
	}
}
