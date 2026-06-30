package runtime

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"github.com/kubercloud/ani/pkg/ports"
)

func TestRegistryPullSecretKubernetesApplyServiceAppliesDockerConfigSecret(t *testing.T) {
	provider := &fakeSecretProviderApply{}
	service := NewRegistryPullSecretKubernetesApplyService(
		&fakeRegistryPullSecretCredentialSource{},
		provider,
	)

	result, err := service.ApplyPullSecretToKubernetes(context.Background(), ports.RegistryPullSecretKubernetesApplyRequest{
		TenantID:       "tenant-a",
		Project:        "tenant-a",
		IdempotencyKey: "pull-k8s-a",
		Name:           "ani-registry-pull",
		Namespace:      "ani-tenant-a",
	})
	if err != nil {
		t.Fatalf("ApplyPullSecretToKubernetes() error = %v", err)
	}
	if !result.KubernetesApplied || result.KubernetesSecretName != "ani-registry-pull" || result.KubernetesNamespace != "ani-tenant-a" {
		t.Fatalf("result = %+v, want applied Kubernetes secret in ani-tenant-a", result)
	}
	if provider.last.Type != "dockerconfigjson" || provider.last.Namespace != "ani-tenant-a" {
		t.Fatalf("provider request = %+v, want dockerconfigjson in ani-tenant-a", provider.last)
	}
	dockerConfig := provider.last.Data[".dockerconfigjson"]
	if !strings.Contains(dockerConfig, `"auths"`) || !strings.Contains(dockerConfig, "registry.local") {
		t.Fatalf("docker config = %s, want registry.local auths", dockerConfig)
	}
}

func TestRegistryPullSecretKubernetesApplyServiceRejectsDuplicateWithoutCredential(t *testing.T) {
	service := NewRegistryPullSecretKubernetesApplyService(
		&fakeRegistryPullSecretCredentialSource{duplicateWithoutPassword: true},
		&fakeSecretProviderApply{},
	)
	_, err := service.ApplyPullSecretToKubernetes(context.Background(), ports.RegistryPullSecretKubernetesApplyRequest{
		TenantID:       "tenant-a",
		Project:        "tenant-a",
		IdempotencyKey: "pull-k8s-dup",
		Namespace:      "ani-tenant-a",
	})
	if err == nil || !strings.Contains(err.Error(), "robot already exists") {
		t.Fatalf("ApplyPullSecretToKubernetes() error = %v, want conflict", err)
	}
}

func TestKubernetesSecretProviderAdapterRendersDockerConfigSecretType(t *testing.T) {
	client := &fakeSecretProviderClient{}
	adapter := NewKubernetesSecretProviderAdapter(client)

	_, err := adapter.ApplySecret(context.Background(), ports.SecretProviderApplyRequest{
		TenantID:  "tenant-a",
		SecretID:  "ani-registry-pull",
		Namespace: "ani-tenant-a",
		Type:      "dockerconfigjson",
		Data:      map[string]string{".dockerconfigjson": `{"auths":{}}`},
	})
	if err != nil {
		t.Fatalf("ApplySecret() error = %v", err)
	}
	var doc map[string]any
	if err := json.Unmarshal([]byte(client.manifests[0].Content), &doc); err != nil {
		t.Fatalf("manifest content is not JSON: %v", err)
	}
	if doc["type"] != "kubernetes.io/dockerconfigjson" {
		t.Fatalf("secret type = %v, want kubernetes.io/dockerconfigjson", doc["type"])
	}
	metadata := doc["metadata"].(map[string]any)
	if metadata["namespace"] != "ani-tenant-a" {
		t.Fatalf("namespace = %v, want ani-tenant-a", metadata["namespace"])
	}
}

type fakeRegistryPullSecretCredentialSource struct {
	duplicateWithoutPassword bool
}

func (f *fakeRegistryPullSecretCredentialSource) CreatePullSecretCredential(_ context.Context, request ports.RegistryPullSecretRequest) (ports.RegistryPullSecret, string, error) {
	if f.duplicateWithoutPassword {
		return ports.RegistryPullSecret{
			Project:  request.Project,
			Name:     "ani-registry-pull",
			Registry: "registry.local",
			Username: "robot$tenant-a",
			State:    ports.RegistryPermissionDuplicate,
		}, "", nil
	}
	return ports.RegistryPullSecret{
		Project:  request.Project,
		Name:     "ani-registry-pull",
		Registry: "registry.local",
		Username: "robot$tenant-a",
		State:    ports.RegistryPermissionActive,
	}, "local-dev-pull-secret", nil
}

var _ ports.RegistryPullSecretCredentialSource = (*fakeRegistryPullSecretCredentialSource)(nil)
