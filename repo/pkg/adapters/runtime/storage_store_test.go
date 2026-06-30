package runtime

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/kubercloud/ani/pkg/ports"
)

const storageStoreTenantID = "5dbb1d01-0000-4000-8000-000000000002"

func TestMetadataStorageStoreUpsertsVolume(t *testing.T) {
	tx := &fakeMetadataTx{}
	store := NewMetadataStorageStore(fakeMetadataStore{tx: tx}, WithStorageStoreClock(func() time.Time {
		return time.Unix(100, 0)
	}))

	err := store.UpsertVolume(context.Background(), ports.StorageVolumeRecord{
		TenantID:     storageStoreTenantID,
		VolumeID:     "vol-test",
		Name:         "data",
		SizeGiB:      100,
		StorageClass: "fast",
		State:        ports.StorageResourceAvailable,
		Reason:       "created",
		CreatedAt:    time.Unix(90, 0),
	})
	if err != nil {
		t.Fatalf("UpsertVolume() error = %v", err)
	}
	if !strings.Contains(tx.sql, "INSERT INTO storage_volumes") {
		t.Fatalf("sql = %q, want storage_volumes insert", tx.sql)
	}
	if got, want := tx.args[1], "vol-test"; got != want {
		t.Fatalf("volume_id arg = %v, want %s", got, want)
	}
	if got, want := tx.args[5], string(ports.StorageResourceAvailable); got != want {
		t.Fatalf("state arg = %v, want %s", got, want)
	}
}

func TestMetadataStorageStoreUpsertsFilesystemAndObject(t *testing.T) {
	tx := &fakeMetadataTx{}
	store := NewMetadataStorageStore(fakeMetadataStore{tx: tx}, WithStorageStoreClock(func() time.Time {
		return time.Unix(100, 0)
	}))

	err := store.UpsertFilesystem(context.Background(), ports.StorageFilesystemRecord{
		TenantID:     storageStoreTenantID,
		FilesystemID: "fs-test",
		Name:         "shared",
		Protocol:     "nfs",
		SizeGiB:      500,
		Endpoint:     "local://shared",
		State:        ports.StorageResourceAvailable,
	})
	if err != nil {
		t.Fatalf("UpsertFilesystem() error = %v", err)
	}
	if !strings.Contains(tx.sql, "INSERT INTO storage_filesystems") {
		t.Fatalf("sql = %q, want storage_filesystems insert", tx.sql)
	}

	err = store.UpsertObject(context.Background(), ports.StorageObjectRecord{
		TenantID:    storageStoreTenantID,
		ObjectID:    "obj-test",
		Bucket:      "models",
		Key:         "llm/model.bin",
		SizeBytes:   1024,
		ContentType: "application/octet-stream",
		State:       ports.StorageResourceAvailable,
	})
	if err != nil {
		t.Fatalf("UpsertObject() error = %v", err)
	}
	if !strings.Contains(tx.sql, "INSERT INTO storage_objects") {
		t.Fatalf("sql = %q, want storage_objects insert", tx.sql)
	}
	if got, want := tx.args[3], "llm/model.bin"; got != want {
		t.Fatalf("object_key arg = %v, want %s", got, want)
	}
}

func TestLocalStorageServicePersistsCreateAndDelete(t *testing.T) {
	tx := &fakeMetadataTx{}
	service := NewLocalStorageService(
		WithStorageResourceStore(NewMetadataStorageStore(fakeMetadataStore{tx: tx})),
	)

	volume, err := service.CreateVolume(context.Background(), ports.StorageVolumeCreateRequest{
		TenantID:       storageStoreTenantID,
		IdempotencyKey: "persisted-volume",
		Name:           "persisted-volume",
		SizeGiB:        10,
	})
	if err != nil {
		t.Fatalf("CreateVolume() error = %v", err)
	}
	tx.row = volumeFakeRow{record: volume}
	if _, err := service.DeleteVolume(context.Background(), ports.StorageResourceGetRequest{
		TenantID:   storageStoreTenantID,
		ResourceID: volume.VolumeID,
	}); err != nil {
		t.Fatalf("DeleteVolume() error = %v", err)
	}
	if len(tx.execs) != 2 {
		t.Fatalf("exec count = %d, want create and delete persistence writes", len(tx.execs))
	}
	if got, want := tx.args[5], string(ports.StorageResourceDeleted); got != want {
		t.Fatalf("last persisted state = %v, want %s", got, want)
	}
}

func TestMetadataStorageStoreUpdatesResourceState(t *testing.T) {
	tx := &fakeMetadataTx{}
	store := NewMetadataStorageStore(fakeMetadataStore{tx: tx}, WithStorageStoreClock(func() time.Time {
		return time.Unix(100, 0)
	}))

	err := store.UpdateResourceState(context.Background(), ports.StorageResourceStateUpdateRequest{
		TenantID:     storageStoreTenantID,
		ResourceKind: "volume",
		ResourceID:   "vol-test",
		State:        ports.StorageResourceFailed,
		Reason:       "PVC lost",
		UpdatedAt:    time.Unix(120, 0),
	})
	if err != nil {
		t.Fatalf("UpdateResourceState() error = %v", err)
	}
	if !strings.Contains(tx.sql, "UPDATE storage_volumes") {
		t.Fatalf("sql = %q, want storage_volumes update", tx.sql)
	}
	if got, want := tx.args[2], string(ports.StorageResourceFailed); got != want {
		t.Fatalf("state arg = %v, want %s", got, want)
	}
}

type volumeFakeRow struct {
	record ports.StorageVolumeRecord
}

func (r volumeFakeRow) Scan(dest ...any) error {
	*dest[0].(*string) = r.record.TenantID
	*dest[1].(*string) = r.record.VolumeID
	*dest[2].(*string) = r.record.Name
	*dest[3].(*int64) = r.record.SizeGiB
	*dest[4].(*string) = r.record.StorageClass
	*dest[5].(*string) = string(r.record.State)
	*dest[6].(*string) = r.record.Reason
	*dest[7].(*time.Time) = r.record.CreatedAt
	*dest[8].(*time.Time) = r.record.UpdatedAt
	return nil
}
