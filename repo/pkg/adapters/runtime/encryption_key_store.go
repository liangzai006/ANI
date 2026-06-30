package runtime

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/kubercloud/ani/pkg/ports"
)

type MetadataEncryptionKeyStore struct {
	store ports.MetadataStore
	now   func() time.Time
}

type EncryptionKeyStoreOption func(*MetadataEncryptionKeyStore)

func WithEncryptionKeyStoreClock(now func() time.Time) EncryptionKeyStoreOption {
	return func(store *MetadataEncryptionKeyStore) {
		if now != nil {
			store.now = now
		}
	}
}

func NewMetadataEncryptionKeyStore(store ports.MetadataStore, options ...EncryptionKeyStoreOption) *MetadataEncryptionKeyStore {
	keyStore := &MetadataEncryptionKeyStore{
		store: store,
		now:   time.Now,
	}
	for _, option := range options {
		option(keyStore)
	}
	return keyStore
}

func (s *MetadataEncryptionKeyStore) UpsertEncryptionKey(ctx context.Context, record ports.EncryptionKeyRecord, idempotencyKey string) error {
	if s.store == nil {
		return ports.ErrNotConfigured
	}
	if err := requireEncryptionKeyTenant(record.TenantID); err != nil {
		return err
	}
	keyID := strings.TrimSpace(record.KeyID)
	name := strings.TrimSpace(record.Name)
	if keyID == "" || name == "" {
		return fmt.Errorf("%w: encryption key id and name are required", ports.ErrInvalid)
	}
	algorithm := strings.TrimSpace(record.Algorithm)
	if algorithm == "" {
		algorithm = "SM4"
	}
	state := strings.TrimSpace(record.State)
	if state == "" {
		state = "active"
	}
	provider := strings.TrimSpace(record.Provider)
	if provider == "" {
		provider = "local"
	}
	refsJSON, err := json.Marshal(record.ProviderRefs)
	if err != nil {
		return fmt.Errorf("marshal encryption key provider refs: %w", err)
	}
	createdAt, updatedAt := secretUnixTimes(s.now, record.CreatedAt, record.UpdatedAt)
	idemKey := strings.TrimSpace(idempotencyKey)
	return s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		_, err := tx.Exec(ctx, `
			INSERT INTO encryption_keys (
				tenant_id, key_id, name, algorithm, state, provider, real_provider, provider_refs,
				idempotency_key, created_at, updated_at
			)
			VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8::jsonb, NULLIF($9, ''), $10, $11)
			ON CONFLICT (tenant_id, key_id) DO UPDATE SET
				name = EXCLUDED.name,
				algorithm = EXCLUDED.algorithm,
				state = EXCLUDED.state,
				provider = EXCLUDED.provider,
				real_provider = EXCLUDED.real_provider,
				provider_refs = EXCLUDED.provider_refs,
				idempotency_key = COALESCE(NULLIF(EXCLUDED.idempotency_key, ''), encryption_keys.idempotency_key),
				updated_at = EXCLUDED.updated_at
		`, record.TenantID, keyID, name, algorithm, state, provider, record.RealProvider, string(refsJSON), idemKey, createdAt, updatedAt)
		if err != nil {
			return fmt.Errorf("upsert encryption key: %w", err)
		}
		return nil
	})
}

func (s *MetadataEncryptionKeyStore) GetEncryptionKey(ctx context.Context, tenantID, keyID string) (ports.EncryptionKeyRecord, error) {
	if s.store == nil {
		return ports.EncryptionKeyRecord{}, ports.ErrNotConfigured
	}
	if err := requireEncryptionKeyTenant(tenantID); err != nil {
		return ports.EncryptionKeyRecord{}, err
	}
	keyID = strings.TrimSpace(keyID)
	if keyID == "" {
		return ports.EncryptionKeyRecord{}, fmt.Errorf("%w: key_id is required", ports.ErrInvalid)
	}
	var record ports.EncryptionKeyRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		return scanEncryptionKeyRow(tx.QueryRow(ctx, `
			SELECT key_id, name, algorithm, state, provider, real_provider, provider_refs, created_at, updated_at
			FROM encryption_keys
			WHERE tenant_id = $1::uuid AND key_id = $2
		`, tenantID, keyID), tenantID, &record)
	})
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return ports.EncryptionKeyRecord{}, ports.ErrNotFound
		}
		return ports.EncryptionKeyRecord{}, err
	}
	return record, nil
}

func (s *MetadataEncryptionKeyStore) ListEncryptionKeys(ctx context.Context, tenantID string) ([]ports.EncryptionKeyRecord, error) {
	if s.store == nil {
		return nil, ports.ErrNotConfigured
	}
	if err := requireEncryptionKeyTenant(tenantID); err != nil {
		return nil, err
	}
	var records []ports.EncryptionKeyRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		rows, err := tx.Query(ctx, `
			SELECT key_id, name, algorithm, state, provider, real_provider, provider_refs, created_at, updated_at
			FROM encryption_keys
			WHERE tenant_id = $1::uuid
			ORDER BY created_at ASC
		`, tenantID)
		if err != nil {
			return fmt.Errorf("list encryption keys: %w", err)
		}
		defer rows.Close()
		for rows.Next() {
			var record ports.EncryptionKeyRecord
			if err := scanEncryptionKeyRows(rows, tenantID, &record); err != nil {
				return err
			}
			records = append(records, record)
		}
		return rows.Err()
	})
	return records, err
}

func (s *MetadataEncryptionKeyStore) GetEncryptionKeyByIdempotency(ctx context.Context, tenantID, idempotencyKey string) (ports.EncryptionKeyRecord, error) {
	if s.store == nil {
		return ports.EncryptionKeyRecord{}, ports.ErrNotConfigured
	}
	if err := requireEncryptionKeyTenant(tenantID); err != nil {
		return ports.EncryptionKeyRecord{}, err
	}
	idemKey := strings.TrimSpace(idempotencyKey)
	if idemKey == "" {
		return ports.EncryptionKeyRecord{}, fmt.Errorf("%w: idempotency_key is required", ports.ErrInvalid)
	}
	var record ports.EncryptionKeyRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		return scanEncryptionKeyRow(tx.QueryRow(ctx, `
			SELECT key_id, name, algorithm, state, provider, real_provider, provider_refs, created_at, updated_at
			FROM encryption_keys
			WHERE tenant_id = $1::uuid AND idempotency_key = $2
		`, tenantID, idemKey), tenantID, &record)
	})
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return ports.EncryptionKeyRecord{}, ports.ErrNotFound
		}
		return ports.EncryptionKeyRecord{}, err
	}
	return record, nil
}

func requireEncryptionKeyTenant(tenantID string) error {
	if strings.TrimSpace(tenantID) == "" {
		return fmt.Errorf("%w: tenant_id is required", ports.ErrInvalid)
	}
	return nil
}

func scanEncryptionKeyRow(row ports.Row, tenantID string, record *ports.EncryptionKeyRecord) error {
	var refsJSON []byte
	var createdAt time.Time
	var updatedAt time.Time
	if err := row.Scan(
		&record.KeyID, &record.Name, &record.Algorithm, &record.State,
		&record.Provider, &record.RealProvider, &refsJSON, &createdAt, &updatedAt,
	); err != nil {
		return err
	}
	record.TenantID = tenantID
	record.ProviderRefs = decodeStringSliceJSON(refsJSON)
	record.CreatedAt = createdAt.Unix()
	record.UpdatedAt = updatedAt.Unix()
	return nil
}

func scanEncryptionKeyRows(rows ports.Rows, tenantID string, record *ports.EncryptionKeyRecord) error {
	var refsJSON []byte
	var createdAt time.Time
	var updatedAt time.Time
	if err := rows.Scan(
		&record.KeyID, &record.Name, &record.Algorithm, &record.State,
		&record.Provider, &record.RealProvider, &refsJSON, &createdAt, &updatedAt,
	); err != nil {
		return err
	}
	record.TenantID = tenantID
	record.ProviderRefs = decodeStringSliceJSON(refsJSON)
	record.CreatedAt = createdAt.Unix()
	record.UpdatedAt = updatedAt.Unix()
	return nil
}

var _ ports.EncryptionKeyResourceStore = (*MetadataEncryptionKeyStore)(nil)
