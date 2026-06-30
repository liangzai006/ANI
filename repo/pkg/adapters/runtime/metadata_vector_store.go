package runtime

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/kubercloud/ani/pkg/ports"
)

type MetadataVectorStoreMetadataStore struct {
	store ports.MetadataStore
	now   func() time.Time
}

type VectorStoreMetadataStoreOption func(*MetadataVectorStoreMetadataStore)

func WithVectorStoreMetadataStoreClock(now func() time.Time) VectorStoreMetadataStoreOption {
	return func(store *MetadataVectorStoreMetadataStore) {
		if now != nil {
			store.now = now
		}
	}
}

func NewMetadataVectorStoreMetadataStore(store ports.MetadataStore, options ...VectorStoreMetadataStoreOption) *MetadataVectorStoreMetadataStore {
	metadataStore := &MetadataVectorStoreMetadataStore{
		store: store,
		now:   time.Now,
	}
	for _, option := range options {
		option(metadataStore)
	}
	return metadataStore
}

func (s *MetadataVectorStoreMetadataStore) UpsertVectorStore(ctx context.Context, record ports.VectorStoreRecord, idempotencyKey string) error {
	if s.store == nil {
		return ports.ErrNotConfigured
	}
	if err := requireVectorStoreRecord(record); err != nil {
		return err
	}
	createdAt, updatedAt := networkRecordTimes(s.now, record.CreatedAt, record.UpdatedAt)
	return s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		_, err := tx.Exec(ctx, `
			INSERT INTO vector_stores (
				tenant_id, store_id, name, dimension, metric, state, reason,
				idempotency_key, created_at, updated_at
			)
			VALUES ($1::uuid, $2, $3, $4, $5, $6, NULLIF($7, ''), NULLIF($8, ''), $9, $10)
			ON CONFLICT (tenant_id, store_id) DO UPDATE SET
				name = EXCLUDED.name,
				dimension = EXCLUDED.dimension,
				metric = EXCLUDED.metric,
				state = EXCLUDED.state,
				reason = EXCLUDED.reason,
				updated_at = EXCLUDED.updated_at
		`, record.TenantID, record.StoreID, record.Name, record.Dimension, record.Metric,
			string(record.State), record.Reason, strings.TrimSpace(idempotencyKey), createdAt, updatedAt)
		if err != nil {
			return fmt.Errorf("upsert vector store: %w", err)
		}
		return nil
	})
}

func (s *MetadataVectorStoreMetadataStore) ListVectorStores(ctx context.Context, tenantID string) ([]ports.VectorStoreRecord, error) {
	if s.store == nil {
		return nil, ports.ErrNotConfigured
	}
	if strings.TrimSpace(tenantID) == "" {
		return nil, fmt.Errorf("%w: tenant_id is required", ports.ErrInvalid)
	}
	var records []ports.VectorStoreRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		rows, err := tx.Query(ctx, `
			SELECT tenant_id::text, store_id, name, dimension, metric, state,
				COALESCE(reason, ''), created_at, updated_at
			FROM vector_stores
			WHERE tenant_id = $1::uuid AND state <> 'deleted'
			ORDER BY updated_at DESC
		`, tenantID)
		if err != nil {
			return err
		}
		defer rows.Close()
		for rows.Next() {
			var record ports.VectorStoreRecord
			if err := scanVectorStoreRecord(rows, &record); err != nil {
				return err
			}
			records = append(records, record)
		}
		return rows.Err()
	})
	if err != nil {
		return nil, err
	}
	return records, nil
}

func (s *MetadataVectorStoreMetadataStore) GetVectorStore(ctx context.Context, tenantID string, storeID string) (ports.VectorStoreRecord, error) {
	if s.store == nil {
		return ports.VectorStoreRecord{}, ports.ErrNotConfigured
	}
	if strings.TrimSpace(tenantID) == "" || strings.TrimSpace(storeID) == "" {
		return ports.VectorStoreRecord{}, fmt.Errorf("%w: tenant_id and store_id are required", ports.ErrInvalid)
	}
	var record ports.VectorStoreRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		row := tx.QueryRow(ctx, `
			SELECT tenant_id::text, store_id, name, dimension, metric, state,
				COALESCE(reason, ''), created_at, updated_at
			FROM vector_stores
			WHERE tenant_id = $1::uuid AND store_id = $2 AND state <> 'deleted'
		`, tenantID, storeID)
		return scanVectorStoreRecord(row, &record)
	})
	if err != nil {
		return ports.VectorStoreRecord{}, err
	}
	return record, nil
}

func requireVectorStoreRecord(record ports.VectorStoreRecord) error {
	if strings.TrimSpace(record.TenantID) == "" {
		return fmt.Errorf("%w: tenant_id is required", ports.ErrInvalid)
	}
	if strings.TrimSpace(record.StoreID) == "" {
		return fmt.Errorf("%w: store_id is required", ports.ErrInvalid)
	}
	if strings.TrimSpace(record.Name) == "" {
		return fmt.Errorf("%w: name is required", ports.ErrInvalid)
	}
	if record.Dimension <= 0 {
		return fmt.Errorf("%w: dimension must be greater than zero", ports.ErrInvalid)
	}
	if record.State == "" {
		return fmt.Errorf("%w: state is required", ports.ErrInvalid)
	}
	return nil
}

func scanVectorStoreRecord(row ports.Row, record *ports.VectorStoreRecord) error {
	var state string
	if err := row.Scan(
		&record.TenantID,
		&record.StoreID,
		&record.Name,
		&record.Dimension,
		&record.Metric,
		&state,
		&record.Reason,
		&record.CreatedAt,
		&record.UpdatedAt,
	); err != nil {
		return ports.ErrNotFound
	}
	record.State = ports.VectorStoreState(state)
	return nil
}

var _ ports.VectorStoreMetadataStore = (*MetadataVectorStoreMetadataStore)(nil)
