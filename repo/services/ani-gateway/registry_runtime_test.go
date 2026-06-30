package main

import (
	"testing"

	"github.com/kubercloud/ani/pkg/adapters/postgres"
	"github.com/kubercloud/ani/pkg/adapters/registry"
)

func TestGatewayImageRegistryDefaultsToRouterLocalProfile(t *testing.T) {
	service, err := newGatewayImageRegistry(gatewayRegistryRuntimeConfig{}, nil)
	if err != nil {
		t.Fatalf("newGatewayImageRegistry() error = %v", err)
	}
	if service != nil {
		t.Fatalf("service = %T, want nil so router keeps local profile", service)
	}
}

func TestGatewayImageRegistryUsesMetadataStoreForLocalProfile(t *testing.T) {
	store := postgres.NewMetadataStore(nil)
	service, err := newGatewayImageRegistry(gatewayRegistryRuntimeConfig{}, store)
	if err != nil {
		t.Fatalf("newGatewayImageRegistry() error = %v", err)
	}
	if _, ok := service.(*registry.PersistingImageRegistry); !ok {
		t.Fatalf("service = %T, want PersistingImageRegistry when metadata store is configured", service)
	}
}

func TestGatewayImageRegistryUsesHarborProvider(t *testing.T) {
	service, err := newGatewayImageRegistry(gatewayRegistryRuntimeConfig{
		Provider: "harbor",
		Endpoint: "https://harbor.example.test",
		Username: "robot",
		Password: "secret",
		Secure:   true,
	}, nil)
	if err != nil {
		t.Fatalf("newGatewayImageRegistry() error = %v", err)
	}
	if service == nil {
		t.Fatal("service = nil, want harbor-backed image registry")
	}
	if _, ok := service.(*registry.HarborImageRegistry); !ok {
		t.Fatalf("service = %T, want HarborImageRegistry without metadata store", service)
	}
}

func TestGatewayImageRegistryWrapsHarborWithMetadataStore(t *testing.T) {
	store := postgres.NewMetadataStore(nil)
	service, err := newGatewayImageRegistry(gatewayRegistryRuntimeConfig{
		Provider: "harbor",
		Endpoint: "https://harbor.example.test",
		Username: "robot",
		Password: "secret",
	}, store)
	if err != nil {
		t.Fatalf("newGatewayImageRegistry() error = %v", err)
	}
	if _, ok := service.(*registry.PersistingImageRegistry); !ok {
		t.Fatalf("service = %T, want PersistingImageRegistry wrapping harbor", service)
	}
}

func TestGatewayImageRegistryRejectsHarborWithoutCredentials(t *testing.T) {
	if _, err := newGatewayImageRegistry(gatewayRegistryRuntimeConfig{
		Provider: "harbor",
		Endpoint: "https://harbor.example.test",
	}, nil); err == nil {
		t.Fatal("newGatewayImageRegistry() error = nil, want missing credential error")
	}
}

func TestGatewayImageRegistryRejectsUnsupportedProvider(t *testing.T) {
	if _, err := newGatewayImageRegistry(gatewayRegistryRuntimeConfig{Provider: "quay"}, nil); err == nil {
		t.Fatal("newGatewayImageRegistry() error = nil, want unsupported provider error")
	}
}

func TestGatewayRegistryConfigFromEnv(t *testing.T) {
	t.Setenv("REGISTRY_PROVIDER", "harbor")
	t.Setenv("REGISTRY_ENDPOINT", "https://harbor.example.test")
	t.Setenv("REGISTRY_USERNAME", "robot")
	t.Setenv("REGISTRY_PASSWORD", "secret")
	t.Setenv("REGISTRY_SECURE", "true")

	cfg := gatewayRegistryRuntimeConfigFromEnv()
	if cfg.Provider != "harbor" || cfg.Endpoint != "https://harbor.example.test" || cfg.Username != "robot" {
		t.Fatalf("registry config not loaded from env: %#v", cfg)
	}
	if !cfg.Secure {
		t.Fatalf("registry secure flag = %v, want true", cfg.Secure)
	}
}
