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

type MetadataSecretStore struct {
	store ports.MetadataStore
	now   func() time.Time
}

type SecretStoreOption func(*MetadataSecretStore)

func WithSecretStoreClock(now func() time.Time) SecretStoreOption {
	return func(store *MetadataSecretStore) {
		if now != nil {
			store.now = now
		}
	}
}

func NewMetadataSecretStore(store ports.MetadataStore, options ...SecretStoreOption) *MetadataSecretStore {
	secretStore := &MetadataSecretStore{
		store: store,
		now:   time.Now,
	}
	for _, option := range options {
		option(secretStore)
	}
	return secretStore
}

func (s *MetadataSecretStore) UpsertSecret(ctx context.Context, record ports.SecretRecord, idempotencyKey string) error {
	if s.store == nil {
		return ports.ErrNotConfigured
	}
	if err := requireSecretTenant(record.TenantID); err != nil {
		return err
	}
	secretID := strings.TrimSpace(record.SecretID)
	name := strings.TrimSpace(record.Name)
	if secretID == "" || name == "" {
		return fmt.Errorf("%w: secret id and name are required", ports.ErrInvalid)
	}
	secretType := strings.TrimSpace(record.Type)
	if secretType == "" {
		secretType = "opaque"
	}
	state := strings.TrimSpace(record.State)
	if state == "" {
		state = "active"
	}
	provider := strings.TrimSpace(record.Provider)
	if provider == "" {
		provider = "local"
	}
	keysJSON, err := json.Marshal(record.Keys)
	if err != nil {
		return fmt.Errorf("marshal secret keys: %w", err)
	}
	refsJSON, err := json.Marshal(record.ProviderRefs)
	if err != nil {
		return fmt.Errorf("marshal secret provider refs: %w", err)
	}
	createdAt, updatedAt := secretUnixTimes(s.now, record.CreatedAt, record.UpdatedAt)
	idemKey := strings.TrimSpace(idempotencyKey)
	return s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		_, err := tx.Exec(ctx, `
			INSERT INTO secrets (
				tenant_id, secret_id, name, type, keys, state, provider, real_provider, provider_refs,
				idempotency_key, created_at, updated_at
			)
			VALUES ($1::uuid, $2, $3, $4, $5::jsonb, $6, $7, $8, $9::jsonb, NULLIF($10, ''), $11, $12)
			ON CONFLICT (tenant_id, secret_id) DO UPDATE SET
				name = EXCLUDED.name,
				type = EXCLUDED.type,
				keys = EXCLUDED.keys,
				state = EXCLUDED.state,
				provider = EXCLUDED.provider,
				real_provider = EXCLUDED.real_provider,
				provider_refs = EXCLUDED.provider_refs,
				idempotency_key = COALESCE(NULLIF(EXCLUDED.idempotency_key, ''), secrets.idempotency_key),
				updated_at = EXCLUDED.updated_at
		`, record.TenantID, secretID, name, secretType, string(keysJSON), state, provider, record.RealProvider, string(refsJSON), idemKey, createdAt, updatedAt)
		if err != nil {
			return fmt.Errorf("upsert secret: %w", err)
		}
		return nil
	})
}

func (s *MetadataSecretStore) GetSecret(ctx context.Context, tenantID, secretID string) (ports.SecretRecord, error) {
	if s.store == nil {
		return ports.SecretRecord{}, ports.ErrNotConfigured
	}
	if err := requireSecretTenant(tenantID); err != nil {
		return ports.SecretRecord{}, err
	}
	secretID = strings.TrimSpace(secretID)
	if secretID == "" {
		return ports.SecretRecord{}, fmt.Errorf("%w: secret_id is required", ports.ErrInvalid)
	}
	var record ports.SecretRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		return scanSecretRow(tx.QueryRow(ctx, `
			SELECT secret_id, name, type, keys, state, provider, real_provider, provider_refs, created_at, updated_at
			FROM secrets
			WHERE tenant_id = $1::uuid AND secret_id = $2
		`, tenantID, secretID), tenantID, &record)
	})
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return ports.SecretRecord{}, ports.ErrNotFound
		}
		return ports.SecretRecord{}, err
	}
	return record, nil
}

func (s *MetadataSecretStore) ListSecrets(ctx context.Context, tenantID string) ([]ports.SecretRecord, error) {
	if s.store == nil {
		return nil, ports.ErrNotConfigured
	}
	if err := requireSecretTenant(tenantID); err != nil {
		return nil, err
	}
	var records []ports.SecretRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		rows, err := tx.Query(ctx, `
			SELECT secret_id, name, type, keys, state, provider, real_provider, provider_refs, created_at, updated_at
			FROM secrets
			WHERE tenant_id = $1::uuid AND state <> 'deleted'
			ORDER BY created_at ASC
		`, tenantID)
		if err != nil {
			return fmt.Errorf("list secrets: %w", err)
		}
		defer rows.Close()
		for rows.Next() {
			var record ports.SecretRecord
			if err := scanSecretRows(rows, tenantID, &record); err != nil {
				return err
			}
			records = append(records, record)
		}
		return rows.Err()
	})
	return records, err
}

func (s *MetadataSecretStore) GetSecretByIdempotency(ctx context.Context, tenantID, idempotencyKey string) (ports.SecretRecord, error) {
	if s.store == nil {
		return ports.SecretRecord{}, ports.ErrNotConfigured
	}
	if err := requireSecretTenant(tenantID); err != nil {
		return ports.SecretRecord{}, err
	}
	idemKey := strings.TrimSpace(idempotencyKey)
	if idemKey == "" {
		return ports.SecretRecord{}, fmt.Errorf("%w: idempotency_key is required", ports.ErrInvalid)
	}
	var record ports.SecretRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		return scanSecretRow(tx.QueryRow(ctx, `
			SELECT secret_id, name, type, keys, state, provider, real_provider, provider_refs, created_at, updated_at
			FROM secrets
			WHERE tenant_id = $1::uuid AND idempotency_key = $2
		`, tenantID, idemKey), tenantID, &record)
	})
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return ports.SecretRecord{}, ports.ErrNotFound
		}
		return ports.SecretRecord{}, err
	}
	return record, nil
}

func (s *MetadataSecretStore) UpsertSecretBinding(ctx context.Context, record ports.SecretBindingRecord) error {
	if s.store == nil {
		return ports.ErrNotConfigured
	}
	if err := requireSecretTenant(record.TenantID); err != nil {
		return err
	}
	bindingID := strings.TrimSpace(record.BindingID)
	secretID := strings.TrimSpace(record.SecretID)
	targetType := strings.TrimSpace(record.TargetType)
	targetID := strings.TrimSpace(record.TargetID)
	if bindingID == "" || secretID == "" || targetType == "" || targetID == "" {
		return fmt.Errorf("%w: binding id, secret id, target type and target id are required", ports.ErrInvalid)
	}
	state := strings.TrimSpace(record.State)
	if state == "" {
		state = "bound"
	}
	createdAt, updatedAt := secretUnixTimes(s.now, record.CreatedAt, record.CreatedAt)
	return s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		_, err := tx.Exec(ctx, `
			INSERT INTO secret_bindings (
				tenant_id, binding_id, secret_id, target_type, target_id, mount_path, env_prefix, state, created_at, updated_at
			)
			VALUES ($1::uuid, $2, $3, $4, $5, NULLIF($6, ''), NULLIF($7, ''), $8, $9, $10)
			ON CONFLICT (tenant_id, binding_id) DO UPDATE SET
				secret_id = EXCLUDED.secret_id,
				target_type = EXCLUDED.target_type,
				target_id = EXCLUDED.target_id,
				mount_path = EXCLUDED.mount_path,
				env_prefix = EXCLUDED.env_prefix,
				state = EXCLUDED.state,
				updated_at = EXCLUDED.updated_at
		`, record.TenantID, bindingID, secretID, targetType, targetID, record.MountPath, record.EnvPrefix, state, createdAt, updatedAt)
		if err != nil {
			return fmt.Errorf("upsert secret binding: %w", err)
		}
		return nil
	})
}

func requireSecretTenant(tenantID string) error {
	if strings.TrimSpace(tenantID) == "" {
		return fmt.Errorf("%w: tenant_id is required", ports.ErrInvalid)
	}
	return nil
}

func secretUnixTimes(now func() time.Time, createdAt int64, updatedAt int64) (time.Time, time.Time) {
	current := time.Now().UTC()
	if now != nil {
		current = now().UTC()
	}
	created := current
	if createdAt > 0 {
		created = time.Unix(createdAt, 0).UTC()
	}
	updated := created
	if updatedAt > 0 {
		updated = time.Unix(updatedAt, 0).UTC()
	}
	return created, updated
}

func scanSecretRow(row ports.Row, tenantID string, record *ports.SecretRecord) error {
	var keysJSON []byte
	var refsJSON []byte
	var createdAt time.Time
	var updatedAt time.Time
	if err := row.Scan(
		&record.SecretID, &record.Name, &record.Type, &keysJSON, &record.State,
		&record.Provider, &record.RealProvider, &refsJSON, &createdAt, &updatedAt,
	); err != nil {
		return err
	}
	record.TenantID = tenantID
	record.Keys = decodeStringSliceJSON(keysJSON)
	record.ProviderRefs = decodeStringSliceJSON(refsJSON)
	record.CreatedAt = createdAt.Unix()
	record.UpdatedAt = updatedAt.Unix()
	return nil
}

func scanSecretRows(rows ports.Rows, tenantID string, record *ports.SecretRecord) error {
	var keysJSON []byte
	var refsJSON []byte
	var createdAt time.Time
	var updatedAt time.Time
	if err := rows.Scan(
		&record.SecretID, &record.Name, &record.Type, &keysJSON, &record.State,
		&record.Provider, &record.RealProvider, &refsJSON, &createdAt, &updatedAt,
	); err != nil {
		return err
	}
	record.TenantID = tenantID
	record.Keys = decodeStringSliceJSON(keysJSON)
	record.ProviderRefs = decodeStringSliceJSON(refsJSON)
	record.CreatedAt = createdAt.Unix()
	record.UpdatedAt = updatedAt.Unix()
	return nil
}

var _ ports.SecretResourceStore = (*MetadataSecretStore)(nil)
