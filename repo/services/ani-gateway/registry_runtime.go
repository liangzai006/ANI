package main

import (
	"fmt"
	"os"
	"strings"

	registryadapter "github.com/kubercloud/ani/pkg/adapters/registry"
	runtimeadapter "github.com/kubercloud/ani/pkg/adapters/runtime"
	"github.com/kubercloud/ani/pkg/ports"
)

type gatewayRegistryRuntimeConfig struct {
	Provider    string
	Endpoint    string
	Username    string
	Password    string
	Secure      bool
	TLSInsecure bool
}

func gatewayRegistryRuntimeConfigFromEnv() gatewayRegistryRuntimeConfig {
	return gatewayRegistryRuntimeConfig{
		Provider:    os.Getenv("REGISTRY_PROVIDER"),
		Endpoint:    os.Getenv("REGISTRY_ENDPOINT"),
		Username:    os.Getenv("REGISTRY_USERNAME"),
		Password:    os.Getenv("REGISTRY_PASSWORD"),
		Secure:      strings.EqualFold(strings.TrimSpace(os.Getenv("REGISTRY_SECURE")), "true"),
		TLSInsecure: strings.EqualFold(strings.TrimSpace(os.Getenv("REGISTRY_TLS_INSECURE")), "true"),
	}
}

// newGatewayImageRegistry returns the configured image registry provider.
// When metadata is configured, local profile uses a PG-backed registry wrapper instead of router fallback.
func newGatewayImageRegistry(cfg gatewayRegistryRuntimeConfig, metadata ports.MetadataStore) (ports.ImageRegistry, error) {
	providerMode := "local"
	var inner ports.ImageRegistry
	switch mode := strings.TrimSpace(cfg.Provider); mode {
	case "", "local", "not_configured":
		if metadata == nil {
			return nil, nil
		}
		inner = registryadapter.NewLocalImageRegistry()
	case "harbor":
		harbor, err := registryadapter.NewHarborImageRegistry(registryadapter.HarborImageRegistryConfig{
			Endpoint:    cfg.Endpoint,
			Username:    cfg.Username,
			Password:    cfg.Password,
			Secure:      cfg.Secure,
			TLSInsecure: cfg.TLSInsecure,
		})
		if err != nil {
			return nil, err
		}
		inner = harbor
		providerMode = "harbor"
	default:
		return nil, fmt.Errorf("%w: unsupported REGISTRY_PROVIDER %q", ports.ErrUnsupported, mode)
	}
	if metadata == nil {
		return inner, nil
	}
	return registryadapter.NewPersistingImageRegistry(
		inner,
		runtimeadapter.NewMetadataRegistryStore(metadata),
		providerMode,
	), nil
}
