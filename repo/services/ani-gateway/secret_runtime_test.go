package main

import (
	"context"
	"net/http"
	"strings"
	"testing"

	"github.com/kubercloud/ani/pkg/ports"
)

func TestGatewaySecretServiceFromConfigUsesKubernetesRESTProvider(t *testing.T) {
	t.Setenv("KUBERNETES_CONFIG_AUTO_LOAD", "false")
	t.Setenv("KUBERNETES_API_HOST", "https://kubernetes.example.test")
	t.Setenv("KUBERNETES_PROVIDER_FIELD_MANAGER", "ani-test")

	var gotPath string
	transport := roundTripFunc(func(r *http.Request) (*http.Response, error) {
		gotPath = r.URL.String()
		if r.Method != http.MethodPatch {
			t.Fatalf("method = %s, want PATCH", r.Method)
		}
		return jsonResponse(http.StatusOK, `{"kind":"Secret"}`), nil
	})

	service, err := newGatewaySecretService(gatewaySecretRuntimeConfig{
		ProviderMode:             "kubernetes_rest",
		KubernetesHTTPClient:     &http.Client{Transport: transport},
	}, nil)
	if err != nil {
		t.Fatalf("newGatewaySecretService() error = %v", err)
	}
	if service == nil {
		t.Fatalf("service = nil, want Kubernetes-backed secret service")
	}
	_, err = service.CreateSecret(context.Background(), ports.SecretCreateRequest{
		TenantID:       "tenant-a",
		IdempotencyKey: "idem-secret",
		Name:           "db-password",
		Data:           map[string]string{"password": "secret-value"},
	})
	if err != nil {
		t.Fatalf("CreateSecret() error = %v", err)
	}
	if !strings.Contains(gotPath, "/api/v1/namespaces/ani-tenant-tenant-a/secrets/sec-") {
		t.Fatalf("path = %q, want tenant Kubernetes Secret path", gotPath)
	}
}

func TestGatewaySecretServiceFromConfigRejectsInvalidProvider(t *testing.T) {
	if _, err := newGatewaySecretService(gatewaySecretRuntimeConfig{ProviderMode: "unknown"}, nil); err == nil {
		t.Fatalf("newGatewaySecretService() error = nil, want unsupported provider error")
	}
}
