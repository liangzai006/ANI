package runtime

import (
	"context"
	"fmt"
	"strings"

	"github.com/kubercloud/ani/pkg/ports"
)

func (s *MetadataStorageStore) ListVolumes(ctx context.Context, tenantID string) ([]ports.StorageVolumeRecord, error) {
	return listStorageRecords(ctx, s, tenantID, `
		SELECT tenant_id::text, volume_id, name, size_gib, storage_class, state, COALESCE(reason, ''), created_at, updated_at
		FROM storage_volumes
		WHERE tenant_id = $1::uuid AND state <> 'deleted'
		ORDER BY updated_at DESC
	`, scanStorageVolume)
}

func (s *MetadataStorageStore) GetVolume(ctx context.Context, tenantID string, volumeID string) (ports.StorageVolumeRecord, error) {
	return getStorageRecord(ctx, s, tenantID, volumeID, `
		SELECT tenant_id::text, volume_id, name, size_gib, storage_class, state, COALESCE(reason, ''), created_at, updated_at
		FROM storage_volumes
		WHERE tenant_id = $1::uuid AND volume_id = $2 AND state <> 'deleted'
	`, scanStorageVolume)
}

func (s *MetadataStorageStore) ListFilesystems(ctx context.Context, tenantID string) ([]ports.StorageFilesystemRecord, error) {
	return listStorageRecords(ctx, s, tenantID, `
		SELECT tenant_id::text, filesystem_id, name, protocol, size_gib, COALESCE(endpoint, ''), state, COALESCE(reason, ''), created_at, updated_at
		FROM storage_filesystems
		WHERE tenant_id = $1::uuid AND state <> 'deleted'
		ORDER BY updated_at DESC
	`, scanStorageFilesystem)
}

func (s *MetadataStorageStore) GetFilesystem(ctx context.Context, tenantID string, filesystemID string) (ports.StorageFilesystemRecord, error) {
	return getStorageRecord(ctx, s, tenantID, filesystemID, `
		SELECT tenant_id::text, filesystem_id, name, protocol, size_gib, COALESCE(endpoint, ''), state, COALESCE(reason, ''), created_at, updated_at
		FROM storage_filesystems
		WHERE tenant_id = $1::uuid AND filesystem_id = $2 AND state <> 'deleted'
	`, scanStorageFilesystem)
}

func (s *MetadataStorageStore) ListObjects(ctx context.Context, tenantID string) ([]ports.StorageObjectRecord, error) {
	return listStorageRecords(ctx, s, tenantID, `
		SELECT tenant_id::text, object_id, bucket, object_key, size_bytes, content_type, state, COALESCE(reason, ''), created_at, updated_at
		FROM storage_objects
		WHERE tenant_id = $1::uuid AND state <> 'deleted'
		ORDER BY updated_at DESC
	`, scanStorageObject)
}

func (s *MetadataStorageStore) GetObject(ctx context.Context, tenantID string, objectID string) (ports.StorageObjectRecord, error) {
	return getStorageRecord(ctx, s, tenantID, objectID, `
		SELECT tenant_id::text, object_id, bucket, object_key, size_bytes, content_type, state, COALESCE(reason, ''), created_at, updated_at
		FROM storage_objects
		WHERE tenant_id = $1::uuid AND object_id = $2 AND state <> 'deleted'
	`, scanStorageObject)
}

type storageRecordScanner[T any] func(ports.Row, *T) error

func listStorageRecords[T any](ctx context.Context, store *MetadataStorageStore, tenantID string, query string, scan storageRecordScanner[T]) ([]T, error) {
	if store.store == nil {
		return nil, ports.ErrNotConfigured
	}
	if strings.TrimSpace(tenantID) == "" {
		return nil, fmt.Errorf("%w: tenant_id is required", ports.ErrInvalid)
	}
	var records []T
	err := store.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		rows, err := tx.Query(ctx, query, tenantID)
		if err != nil {
			return err
		}
		defer rows.Close()
		for rows.Next() {
			var record T
			if err := scan(rows, &record); err != nil {
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

func getStorageRecord[T any](ctx context.Context, store *MetadataStorageStore, tenantID string, resourceID string, query string, scan storageRecordScanner[T]) (T, error) {
	var zero T
	if store.store == nil {
		return zero, ports.ErrNotConfigured
	}
	if strings.TrimSpace(tenantID) == "" || strings.TrimSpace(resourceID) == "" {
		return zero, fmt.Errorf("%w: tenant_id and resource id are required", ports.ErrInvalid)
	}
	var record T
	err := store.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		row := tx.QueryRow(ctx, query, tenantID, resourceID)
		return scan(row, &record)
	})
	if err != nil {
		return zero, err
	}
	return record, nil
}

func scanStorageVolume(row ports.Row, record *ports.StorageVolumeRecord) error {
	var state string
	if err := row.Scan(&record.TenantID, &record.VolumeID, &record.Name, &record.SizeGiB, &record.StorageClass, &state, &record.Reason, &record.CreatedAt, &record.UpdatedAt); err != nil {
		return ports.ErrNotFound
	}
	record.State = ports.StorageResourceState(state)
	return nil
}

func scanStorageFilesystem(row ports.Row, record *ports.StorageFilesystemRecord) error {
	var state string
	if err := row.Scan(&record.TenantID, &record.FilesystemID, &record.Name, &record.Protocol, &record.SizeGiB, &record.Endpoint, &state, &record.Reason, &record.CreatedAt, &record.UpdatedAt); err != nil {
		return ports.ErrNotFound
	}
	record.State = ports.StorageResourceState(state)
	return nil
}

func scanStorageObject(row ports.Row, record *ports.StorageObjectRecord) error {
	var state string
	if err := row.Scan(&record.TenantID, &record.ObjectID, &record.Bucket, &record.Key, &record.SizeBytes, &record.ContentType, &state, &record.Reason, &record.CreatedAt, &record.UpdatedAt); err != nil {
		return ports.ErrNotFound
	}
	record.State = ports.StorageResourceState(state)
	return nil
}
