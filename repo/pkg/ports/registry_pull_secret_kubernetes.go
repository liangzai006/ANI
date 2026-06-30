package ports

import (
	"context"
	"time"
)

// RegistryPullSecretCredentialSource creates a registry robot account and returns the one-time password.
// The password is only available on first creation; duplicate robot names return empty password.
type RegistryPullSecretCredentialSource interface {
	CreatePullSecretCredential(ctx context.Context, request RegistryPullSecretRequest) (RegistryPullSecret, string, error)
}

type RegistryPullSecretKubernetesApplyRequest struct {
	TenantID       string
	Project        string
	IdempotencyKey string
	Name           string
	Namespace      string
}

type RegistryPullSecretKubernetesApplyResult struct {
	RegistryPullSecret
	KubernetesSecretName string
	KubernetesNamespace  string
	KubernetesApplied    bool
	ProviderRefs         []string
	AppliedAt            time.Time
}

type RegistryPullSecretKubernetesApply interface {
	ApplyPullSecretToKubernetes(ctx context.Context, request RegistryPullSecretKubernetesApplyRequest) (RegistryPullSecretKubernetesApplyResult, error)
}
