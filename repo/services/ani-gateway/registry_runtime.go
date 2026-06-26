package main

import (
	"fmt"
	"os"
	"strings"

	registryadapter "github.com/kubercloud/ani/pkg/adapters/registry"
	"github.com/kubercloud/ani/pkg/ports"
)

type gatewayRegistryRuntimeConfig struct {
	Provider string
	Endpoint string
	Username string
	Password string
	Secure   bool
}

func gatewayRegistryRuntimeConfigFromEnv() gatewayRegistryRuntimeConfig {
	return gatewayRegistryRuntimeConfig{
		Provider: os.Getenv("REGISTRY_PROVIDER"),
		Endpoint: os.Getenv("REGISTRY_ENDPOINT"),
		Username: os.Getenv("REGISTRY_USERNAME"),
		Password: os.Getenv("REGISTRY_PASSWORD"),
		Secure:   strings.EqualFold(strings.TrimSpace(os.Getenv("REGISTRY_SECURE")), "true"),
	}
}

// newGatewayImageRegistry returns the configured image registry provider, or nil so the
// router keeps its built-in local profile when no real provider is selected.
func newGatewayImageRegistry(cfg gatewayRegistryRuntimeConfig) (ports.ImageRegistry, error) {
	switch mode := strings.TrimSpace(cfg.Provider); mode {
	case "", "local", "not_configured":
		return nil, nil
	case "harbor":
		return registryadapter.NewHarborImageRegistry(registryadapter.HarborImageRegistryConfig{
			Endpoint: cfg.Endpoint,
			Username: cfg.Username,
			Password: cfg.Password,
			Secure:   cfg.Secure,
		})
	default:
		return nil, fmt.Errorf("%w: unsupported REGISTRY_PROVIDER %q", ports.ErrUnsupported, mode)
	}
}
