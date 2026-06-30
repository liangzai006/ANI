package runtime

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/kubercloud/ani/pkg/ports"
)

func (s *MetadataStorageStore) UpsertBucket(ctx context.Context, record ports.StorageBucketRecord, idempotencyKey string) error {
	if s.store == nil {
		return ports.ErrNotConfigured
	}
	if strings.TrimSpace(record.TenantID) == "" || strings.TrimSpace(record.BucketID) == "" || strings.TrimSpace(record.Name) == "" {
		return fmt.Errorf("%w: tenant_id, bucket_id and name are required", ports.ErrInvalid)
	}
	createdAt, updatedAt := networkRecordTimes(s.now, record.CreatedAt, time.Time{})
	return s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		_, err := tx.Exec(ctx, `
			INSERT INTO storage_buckets (
				tenant_id, bucket_id, name, region, access_mode, idempotency_key, created_at, updated_at
			)
			VALUES ($1::uuid, $2, $3, NULLIF($4, ''), $5, NULLIF($6, ''), $7, $8)
			ON CONFLICT (tenant_id, bucket_id) DO UPDATE SET
				name = EXCLUDED.name,
				region = EXCLUDED.region,
				access_mode = EXCLUDED.access_mode,
				updated_at = EXCLUDED.updated_at
		`, record.TenantID, record.BucketID, record.Name, record.Region, record.AccessMode,
			idempotencyClientKey(idempotencyKey), createdAt, updatedAt)
		if err != nil {
			return fmt.Errorf("upsert storage bucket: %w", err)
		}
		return nil
	})
}

func (s *MetadataStorageStore) UpsertVolumeSnapshot(ctx context.Context, record ports.VolumeSnapshotRecord, idempotencyKey string) error {
	if s.store == nil {
		return ports.ErrNotConfigured
	}
	if strings.TrimSpace(record.TenantID) == "" || strings.TrimSpace(record.SnapshotID) == "" {
		return fmt.Errorf("%w: tenant_id and snapshot_id are required", ports.ErrInvalid)
	}
	createdAt, updatedAt := networkRecordTimes(s.now, record.CreatedAt, time.Time{})
	return s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		_, err := tx.Exec(ctx, `
			INSERT INTO volume_snapshots (
				tenant_id, snapshot_id, volume_id, name, description, status, size_bytes,
				idempotency_key, created_at, updated_at
			)
			VALUES ($1::uuid, $2, $3, $4, NULLIF($5, ''), $6, $7, NULLIF($8, ''), $9, $10)
			ON CONFLICT (tenant_id, snapshot_id) DO UPDATE SET
				status = EXCLUDED.status,
				size_bytes = EXCLUDED.size_bytes,
				description = EXCLUDED.description,
				updated_at = EXCLUDED.updated_at
		`, record.TenantID, record.SnapshotID, record.VolumeID, record.Name, record.Description,
			string(record.Status), record.SizeBytes, idempotencyClientKey(idempotencyKey), createdAt, updatedAt)
		if err != nil {
			return fmt.Errorf("upsert volume snapshot: %w", err)
		}
		return nil
	})
}

func (s *MetadataStorageStore) UpsertFilesystemMountTarget(ctx context.Context, record ports.FilesystemMountTargetRecord) error {
	if s.store == nil {
		return ports.ErrNotConfigured
	}
	if strings.TrimSpace(record.TenantID) == "" || strings.TrimSpace(record.MountTargetID) == "" {
		return fmt.Errorf("%w: tenant_id and mount_target_id are required", ports.ErrInvalid)
	}
	createdAt, updatedAt := networkRecordTimes(s.now, record.CreatedAt, time.Time{})
	return s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		_, err := tx.Exec(ctx, `
			INSERT INTO filesystem_mount_targets (
				tenant_id, mount_target_id, filesystem_id, subnet_id, ip_address, status, created_at, updated_at
			)
			VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8)
			ON CONFLICT (tenant_id, filesystem_id) DO UPDATE SET
				subnet_id = EXCLUDED.subnet_id,
				ip_address = EXCLUDED.ip_address,
				status = EXCLUDED.status,
				updated_at = EXCLUDED.updated_at
		`, record.TenantID, record.MountTargetID, record.FilesystemID, record.SubnetID, record.IPAddress,
			string(record.Status), createdAt, updatedAt)
		if err != nil {
			return fmt.Errorf("upsert filesystem mount target: %w", err)
		}
		return nil
	})
}

func (s *MetadataStorageStore) ListBuckets(ctx context.Context, tenantID string) ([]ports.StorageBucketRecord, error) {
	if s.store == nil {
		return nil, ports.ErrNotConfigured
	}
	if strings.TrimSpace(tenantID) == "" {
		return nil, fmt.Errorf("%w: tenant_id is required", ports.ErrInvalid)
	}
	var records []ports.StorageBucketRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		rows, err := tx.Query(ctx, `
			SELECT b.tenant_id::text, b.bucket_id, b.name, COALESCE(b.region, ''), b.access_mode, b.created_at,
				COALESCE(COUNT(o.object_id), 0),
				COALESCE(SUM(o.size_bytes), 0)
			FROM storage_buckets b
			LEFT JOIN storage_objects o
				ON o.tenant_id = b.tenant_id AND o.bucket = b.name AND o.state <> 'deleted'
			WHERE b.tenant_id = $1::uuid
			GROUP BY b.tenant_id, b.bucket_id, b.name, b.region, b.access_mode, b.created_at
			ORDER BY b.created_at DESC
		`, tenantID)
		if err != nil {
			return err
		}
		defer rows.Close()
		for rows.Next() {
			var record ports.StorageBucketRecord
			var objectCount int64
			if err := rows.Scan(&record.TenantID, &record.BucketID, &record.Name, &record.Region,
				&record.AccessMode, &record.CreatedAt, &objectCount, &record.SizeBytes); err != nil {
				return err
			}
			record.ObjectCount = int(objectCount)
			records = append(records, record)
		}
		return rows.Err()
	})
	if err != nil {
		return nil, err
	}
	return records, nil
}

func (s *MetadataStorageStore) GetBucket(ctx context.Context, tenantID string, bucketID string) (ports.StorageBucketRecord, error) {
	return getStorageBucket(ctx, s, `
		SELECT tenant_id::text, bucket_id, name, COALESCE(region, ''), access_mode, created_at
		FROM storage_buckets
		WHERE tenant_id = $1::uuid AND bucket_id = $2
	`, tenantID, bucketID)
}

func (s *MetadataStorageStore) GetBucketByName(ctx context.Context, tenantID string, name string) (ports.StorageBucketRecord, error) {
	return getStorageBucket(ctx, s, `
		SELECT tenant_id::text, bucket_id, name, COALESCE(region, ''), access_mode, created_at
		FROM storage_buckets
		WHERE tenant_id = $1::uuid AND name = $2
	`, tenantID, name)
}

func getStorageBucket(ctx context.Context, store *MetadataStorageStore, query string, tenantID string, key string) (ports.StorageBucketRecord, error) {
	var record ports.StorageBucketRecord
	if store.store == nil {
		return record, ports.ErrNotConfigured
	}
	err := store.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		row := tx.QueryRow(ctx, query, tenantID, key)
		return row.Scan(&record.TenantID, &record.BucketID, &record.Name, &record.Region, &record.AccessMode, &record.CreatedAt)
	})
	if err != nil {
		return ports.StorageBucketRecord{}, ports.ErrNotFound
	}
	return record, nil
}

func (s *MetadataStorageStore) ListVolumeSnapshots(ctx context.Context, tenantID string, volumeID string) ([]ports.VolumeSnapshotRecord, error) {
	if s.store == nil {
		return nil, ports.ErrNotConfigured
	}
	if strings.TrimSpace(tenantID) == "" || strings.TrimSpace(volumeID) == "" {
		return nil, fmt.Errorf("%w: tenant_id and volume_id are required", ports.ErrInvalid)
	}
	var records []ports.VolumeSnapshotRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		rows, err := tx.Query(ctx, `
			SELECT tenant_id::text, snapshot_id, volume_id, name, COALESCE(description, ''), status, size_bytes, created_at
			FROM volume_snapshots
			WHERE tenant_id = $1::uuid AND volume_id = $2 AND status <> 'deleting'
			ORDER BY created_at DESC
		`, tenantID, volumeID)
		if err != nil {
			return err
		}
		defer rows.Close()
		for rows.Next() {
			var record ports.VolumeSnapshotRecord
			var status string
			if err := rows.Scan(&record.TenantID, &record.SnapshotID, &record.VolumeID, &record.Name,
				&record.Description, &status, &record.SizeBytes, &record.CreatedAt); err != nil {
				return err
			}
			record.Status = ports.VolumeSnapshotStatus(status)
			records = append(records, record)
		}
		return rows.Err()
	})
	if err != nil {
		return nil, err
	}
	return records, nil
}

func (s *MetadataStorageStore) GetVolumeSnapshotByIdempotency(ctx context.Context, tenantID string, idempotencyKey string) (ports.VolumeSnapshotRecord, error) {
	if s.store == nil {
		return ports.VolumeSnapshotRecord{}, ports.ErrNotConfigured
	}
	clientKey := idempotencyClientKey(idempotencyKey)
	var record ports.VolumeSnapshotRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		row := tx.QueryRow(ctx, `
			SELECT tenant_id::text, snapshot_id, volume_id, name, COALESCE(description, ''), status, size_bytes, created_at
			FROM volume_snapshots
			WHERE tenant_id = $1::uuid AND idempotency_key = $2
		`, tenantID, clientKey)
		var status string
		if err := row.Scan(&record.TenantID, &record.SnapshotID, &record.VolumeID, &record.Name,
			&record.Description, &status, &record.SizeBytes, &record.CreatedAt); err != nil {
			return ports.ErrNotFound
		}
		record.Status = ports.VolumeSnapshotStatus(status)
		return nil
	})
	if err != nil {
		return ports.VolumeSnapshotRecord{}, err
	}
	return record, nil
}

func (s *MetadataStorageStore) GetBucketByIdempotency(ctx context.Context, tenantID string, idempotencyKey string) (ports.StorageBucketRecord, error) {
	if s.store == nil {
		return ports.StorageBucketRecord{}, ports.ErrNotConfigured
	}
	clientKey := idempotencyClientKey(idempotencyKey)
	var record ports.StorageBucketRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		row := tx.QueryRow(ctx, `
			SELECT tenant_id::text, bucket_id, name, COALESCE(region, ''), access_mode, created_at
			FROM storage_buckets
			WHERE tenant_id = $1::uuid AND idempotency_key = $2
		`, tenantID, clientKey)
		return row.Scan(&record.TenantID, &record.BucketID, &record.Name, &record.Region, &record.AccessMode, &record.CreatedAt)
	})
	if err != nil {
		return ports.StorageBucketRecord{}, ports.ErrNotFound
	}
	return record, nil
}

func (s *MetadataStorageStore) GetFilesystemMountTarget(ctx context.Context, tenantID string, filesystemID string) (ports.FilesystemMountTargetRecord, error) {
	if s.store == nil {
		return ports.FilesystemMountTargetRecord{}, ports.ErrNotConfigured
	}
	var record ports.FilesystemMountTargetRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		row := tx.QueryRow(ctx, `
			SELECT tenant_id::text, mount_target_id, filesystem_id, subnet_id, ip_address, status, created_at
			FROM filesystem_mount_targets
			WHERE tenant_id = $1::uuid AND filesystem_id = $2 AND status <> 'deleting'
		`, tenantID, filesystemID)
		var status string
		if err := row.Scan(&record.TenantID, &record.MountTargetID, &record.FilesystemID, &record.SubnetID,
			&record.IPAddress, &status, &record.CreatedAt); err != nil {
			return ports.ErrNotFound
		}
		record.Status = ports.MountTargetStatus(status)
		return nil
	})
	if err != nil {
		return ports.FilesystemMountTargetRecord{}, err
	}
	return record, nil
}
