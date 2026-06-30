package main

import "testing"

func TestGatewayInstanceObservabilityDefaultsToRouterLocalService(t *testing.T) {
	observability, useName, err := newGatewayInstanceObservability(gatewayInstanceObservabilityRuntimeConfig{})
	if err != nil {
		t.Fatalf("newGatewayInstanceObservability() error = %v", err)
	}
	if observability != nil || useName {
		t.Fatalf("observability=%T useName=%v, want nil/false so router keeps local default", observability, useName)
	}
}

func TestGatewayInstanceObservabilityCanInjectPrometheusProvider(t *testing.T) {
	t.Setenv("KUBERNETES_CONFIG_AUTO_LOAD", "false")
	t.Setenv("KUBERNETES_API_HOST", "https://kubernetes.example")

	observability, useName, err := newGatewayInstanceObservability(gatewayInstanceObservabilityRuntimeConfig{
		Provider:      "prometheus_kubernetes",
		PrometheusURL: "http://prometheus.example:9090",
		ExecBaseURL:   "wss://gateway.example/api/v1",
	})
	if err != nil {
		t.Fatalf("newGatewayInstanceObservability() error = %v", err)
	}
	if observability == nil || !useName {
		t.Fatalf("observability=%T useName=%v, want provider and instance-name targeting", observability, useName)
	}
}

func TestGatewayInstanceObservabilityConfigFromEnv(t *testing.T) {
	t.Setenv("INSTANCE_OBSERVABILITY_PROVIDER", "prometheus_kubernetes")
	t.Setenv("INSTANCE_OBSERVABILITY_PROMETHEUS_URL", "http://prometheus.example:9090")
	t.Setenv("INSTANCE_OBSERVABILITY_EXEC_BASE_URL", "wss://gateway.example/api/v1")
	t.Setenv("KUBERNETES_SERVICE_ACCOUNT_TOKEN_FILE", "/var/run/token")
	t.Setenv("KUBERNETES_SERVICE_ACCOUNT_CA_FILE", "/var/run/ca.crt")

	cfg := gatewayInstanceObservabilityRuntimeConfigFromEnv()
	if cfg.Provider != "prometheus_kubernetes" || cfg.PrometheusURL == "" || cfg.ExecBaseURL == "" {
		t.Fatalf("instance observability env config not loaded: %#v", cfg)
	}
}

func TestGatewayInstanceObservabilityRejectsUnsupportedProvider(t *testing.T) {
	if _, _, err := newGatewayInstanceObservability(gatewayInstanceObservabilityRuntimeConfig{Provider: "prometheus"}); err == nil {
		t.Fatal("newGatewayInstanceObservability() error = nil, want unsupported provider error")
	}
}
