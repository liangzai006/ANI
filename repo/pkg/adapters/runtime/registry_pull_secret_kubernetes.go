package runtime

import (
	"context"
	"fmt"
	"strings"
	"time"

	registryadapter "github.com/kubercloud/ani/pkg/adapters/registry"
	"github.com/kubercloud/ani/pkg/ports"
)

type RegistryPullSecretKubernetesApplyService struct {
	credentials ports.RegistryPullSecretCredentialSource
	provider    ports.SecretProviderApply
	now         func() time.Time
}

func NewRegistryPullSecretKubernetesApplyService(
	credentials ports.RegistryPullSecretCredentialSource,
	provider ports.SecretProviderApply,
	options ...RegistryPullSecretKubernetesApplyOption,
) *RegistryPullSecretKubernetesApplyService {
	service := &RegistryPullSecretKubernetesApplyService{
		credentials: credentials,
		provider:    provider,
		now:         time.Now,
	}
	for _, option := range options {
		option(service)
	}
	return service
}

type RegistryPullSecretKubernetesApplyOption func(*RegistryPullSecretKubernetesApplyService)

func WithRegistryPullSecretKubernetesApplyClock(now func() time.Time) RegistryPullSecretKubernetesApplyOption {
	return func(service *RegistryPullSecretKubernetesApplyService) {
		if now != nil {
			service.now = now
		}
	}
}

func (s *RegistryPullSecretKubernetesApplyService) ApplyPullSecretToKubernetes(
	ctx context.Context,
	request ports.RegistryPullSecretKubernetesApplyRequest,
) (ports.RegistryPullSecretKubernetesApplyResult, error) {
	if s.credentials == nil || s.provider == nil {
		return ports.RegistryPullSecretKubernetesApplyResult{}, fmt.Errorf("%w: registry pull secret Kubernetes apply is not configured", ports.ErrNotConfigured)
	}
	if strings.TrimSpace(request.TenantID) == "" || strings.TrimSpace(request.Project) == "" {
		return ports.RegistryPullSecretKubernetesApplyResult{}, fmt.Errorf("%w: tenant_id and project are required", ports.ErrInvalid)
	}
	if strings.TrimSpace(request.IdempotencyKey) == "" {
		return ports.RegistryPullSecretKubernetesApplyResult{}, fmt.Errorf("%w: idempotency_key is required", ports.ErrInvalid)
	}
	namespace := strings.TrimSpace(request.Namespace)
	if namespace == "" {
		return ports.RegistryPullSecretKubernetesApplyResult{}, fmt.Errorf("%w: namespace is required for Kubernetes pull secret apply", ports.ErrInvalid)
	}
	name := strings.TrimSpace(request.Name)
	if name == "" {
		name = "ani-registry-pull"
	}

	secret, password, err := s.credentials.CreatePullSecretCredential(ctx, ports.RegistryPullSecretRequest{
		TenantID:       request.TenantID,
		Project:        request.Project,
		IdempotencyKey: request.IdempotencyKey,
		Name:           name,
		Namespace:      namespace,
	})
	if err != nil {
		return ports.RegistryPullSecretKubernetesApplyResult{}, err
	}
	if secret.State == ports.RegistryPermissionDuplicate && password == "" {
		return ports.RegistryPullSecretKubernetesApplyResult{}, fmt.Errorf(
			"%w: registry pull secret robot already exists without retrievable credential; use a new name or rotate the robot",
			ports.ErrConflict,
		)
	}
	dockerConfig, err := registryadapter.BuildDockerConfigJSON(secret.Registry, secret.Username, password)
	if err != nil {
		return ports.RegistryPullSecretKubernetesApplyResult{}, err
	}
	if dockerConfig == "" {
		return ports.RegistryPullSecretKubernetesApplyResult{}, fmt.Errorf("%w: registry pull secret credential is empty", ports.ErrInvalid)
	}

	applyResult, err := s.provider.ApplySecret(ctx, ports.SecretProviderApplyRequest{
		TenantID:  request.TenantID,
		SecretID:  name,
		Name:      name,
		Namespace: namespace,
		Type:      "dockerconfigjson",
		Data: map[string]string{
			".dockerconfigjson": dockerConfig,
		},
	})
	if err != nil {
		return ports.RegistryPullSecretKubernetesApplyResult{}, err
	}
	if !applyResult.Applied {
		return ports.RegistryPullSecretKubernetesApplyResult{}, fmt.Errorf("%w: Kubernetes Secret provider did not apply pull secret", ports.ErrNotConfigured)
	}

	return ports.RegistryPullSecretKubernetesApplyResult{
		RegistryPullSecret:   secret,
		KubernetesSecretName: name,
		KubernetesNamespace:  namespace,
		KubernetesApplied:    true,
		ProviderRefs:         append([]string(nil), applyResult.ResourceRefs...),
		AppliedAt:            s.now().UTC(),
	}, nil
}

var _ ports.RegistryPullSecretKubernetesApply = (*RegistryPullSecretKubernetesApplyService)(nil)
