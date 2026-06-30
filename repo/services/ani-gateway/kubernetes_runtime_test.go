package main

import (
	"testing"

	runtimeadapter "github.com/kubercloud/ani/pkg/adapters/runtime"
)

func TestGatewayKubernetesRESTClientConfigFromEnvIncludesInClusterKubernetesService(t *testing.T) {
	t.Setenv("KUBERNETES_SERVICE_HOST", "10.96.0.1")
	t.Setenv("KUBERNETES_SERVICE_PORT", "443")
	t.Setenv("KUBERNETES_SERVICE_ACCOUNT_TOKEN_FILE", "/var/run/secrets/kubernetes.io/serviceaccount/token")
	t.Setenv("KUBERNETES_SERVICE_ACCOUNT_CA_FILE", "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")

	cfg := gatewayKubernetesRESTClientConfig(nil, 0)

	if cfg.ServiceHost != "10.96.0.1" || cfg.ServicePort != "443" {
		t.Fatalf("service host/port = %q/%q, want in-cluster Kubernetes service", cfg.ServiceHost, cfg.ServicePort)
	}
	if cfg.BearerTokenFile == "" || cfg.CAFile == "" {
		t.Fatalf("service account token/CA files = %q/%q, want configured files", cfg.BearerTokenFile, cfg.CAFile)
	}
}

func TestGatewayKubernetesRESTClientConfigFromEnvDelegatesToRuntimeLoader(t *testing.T) {
	t.Setenv("KUBERNETES_API_HOST", "https://kubernetes.example.test")
	t.Setenv("KUBERNETES_PROVIDER_FIELD_MANAGER", "ani-test")

	cfg := gatewayKubernetesRESTClientConfig(nil, 0)
	want := runtimeadapter.LoadKubernetesRESTEnvFromOS().ClientConfig()
	if cfg.Host != want.Host || cfg.FieldManager != want.FieldManager {
		t.Fatalf("cfg = %#v, want runtime env loader output %#v", cfg, want)
	}
}
