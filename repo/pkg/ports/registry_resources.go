package ports

import (
	"context"
	"time"
)

type RegistryProjectRecord struct {
	TenantID     string
	ProjectID    string
	Name         string
	Public       bool
	ProviderMode string
	CreatedAt    time.Time
	UpdatedAt    time.Time
}

type RegistryPermissionRecord struct {
	TenantID   string
	Project    string
	Repository string
	Subject    string
	Actions    []RegistryPermissionAction
	State      RegistryPermissionState
	UpdatedAt  time.Time
}

type RegistryPullSecretRecord struct {
	TenantID  string
	Project   string
	Name      string
	SecretRef string
	Registry  string
	Username  string
	Namespace string
	State     RegistryPermissionState
	CreatedAt time.Time
	UpdatedAt time.Time
}

type RegistryResourceStore interface {
	UpsertProject(ctx context.Context, record RegistryProjectRecord, idempotencyKey string) error
	ListProjects(ctx context.Context, tenantID string) ([]RegistryProjectRecord, error)
	GetProjectByIdempotency(ctx context.Context, tenantID, idempotencyKey string) (RegistryProjectRecord, error)

	UpsertRepositoryPermission(ctx context.Context, record RegistryPermissionRecord, idempotencyKey string) error
	GetPermissionByIdempotency(ctx context.Context, tenantID, idempotencyKey string) (RegistryPermissionRecord, error)
	GetRepositoryPermission(ctx context.Context, tenantID, project, repository, subject string) (RegistryPermissionRecord, error)

	UpsertPullSecret(ctx context.Context, record RegistryPullSecretRecord, idempotencyKey string) error
	GetPullSecretByIdempotency(ctx context.Context, tenantID, idempotencyKey string) (RegistryPullSecretRecord, error)
}
