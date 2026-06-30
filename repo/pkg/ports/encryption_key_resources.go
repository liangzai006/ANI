package ports

import "context"

type EncryptionKeyResourceStore interface {
	UpsertEncryptionKey(ctx context.Context, record EncryptionKeyRecord, idempotencyKey string) error
	GetEncryptionKey(ctx context.Context, tenantID, keyID string) (EncryptionKeyRecord, error)
	ListEncryptionKeys(ctx context.Context, tenantID string) ([]EncryptionKeyRecord, error)
	GetEncryptionKeyByIdempotency(ctx context.Context, tenantID, idempotencyKey string) (EncryptionKeyRecord, error)
}
