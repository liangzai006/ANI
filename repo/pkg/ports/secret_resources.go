package ports

import "context"

type SecretResourceStore interface {
	UpsertSecret(ctx context.Context, record SecretRecord, idempotencyKey string) error
	GetSecret(ctx context.Context, tenantID, secretID string) (SecretRecord, error)
	ListSecrets(ctx context.Context, tenantID string) ([]SecretRecord, error)
	GetSecretByIdempotency(ctx context.Context, tenantID, idempotencyKey string) (SecretRecord, error)

	UpsertSecretBinding(ctx context.Context, record SecretBindingRecord) error
}
