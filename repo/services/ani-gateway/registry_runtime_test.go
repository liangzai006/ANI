package main

import "testing"

func TestGatewayImageRegistryDefaultsToRouterLocalProfile(t *testing.T) {
	service, err := newGatewayImageRegistry(gatewayRegistryRuntimeConfig{})
	if err != nil {
		t.Fatalf("newGatewayImageRegistry() error = %v", err)
	}
	if service != nil {
		t.Fatalf("service = %T, want nil so router keeps local profile", service)
	}
}

func TestGatewayImageRegistryUsesHarborProvider(t *testing.T) {
	service, err := newGatewayImageRegistry(gatewayRegistryRuntimeConfig{
		Provider: "harbor",
		Endpoint: "https://harbor.example.test",
		Username: "robot",
		Password: "secret",
		Secure:   true,
	})
	if err != nil {
		t.Fatalf("newGatewayImageRegistry() error = %v", err)
	}
	if service == nil {
		t.Fatal("service = nil, want harbor-backed image registry")
	}
}

func TestGatewayImageRegistryRejectsHarborWithoutCredentials(t *testing.T) {
	if _, err := newGatewayImageRegistry(gatewayRegistryRuntimeConfig{
		Provider: "harbor",
		Endpoint: "https://harbor.example.test",
	}); err == nil {
		t.Fatal("newGatewayImageRegistry() error = nil, want missing credential error")
	}
}

func TestGatewayImageRegistryRejectsUnsupportedProvider(t *testing.T) {
	if _, err := newGatewayImageRegistry(gatewayRegistryRuntimeConfig{Provider: "quay"}); err == nil {
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
