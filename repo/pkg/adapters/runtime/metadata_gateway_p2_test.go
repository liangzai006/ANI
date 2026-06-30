package runtime

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/kubercloud/ani/pkg/ports"
)

func TestMetadataNetworkStoreListVPCsUsesTenantScopedQuery(t *testing.T) {
	now := time.Unix(200, 0).UTC()
	tx := &fakeMetadataTx{
		row: vpcFakeRow{
			record: ports.NetworkVPCRecord{
				TenantID:  networkStoreTenantID,
				VPCID:     "vpc-read",
				Name:      "read-vpc",
				CIDR:      "10.0.0.0/16",
				State:     ports.NetworkResourceAvailable,
				CreatedAt: now,
				UpdatedAt: now,
			},
		},
	}
	store := NewMetadataNetworkStore(fakeMetadataStore{tx: tx})
	record, err := store.GetVPC(context.Background(), networkStoreTenantID, "vpc-read")
	if err != nil {
		t.Fatalf("GetVPC() error = %v", err)
	}
	if record.Name != "read-vpc" {
		t.Fatalf("name = %q, want read-vpc", record.Name)
	}
	if !strings.Contains(tx.queryRowSQL, "FROM network_vpcs") {
		t.Fatalf("query = %q, want network_vpcs select", tx.queryRowSQL)
	}
}

func TestLocalNetworkServiceGetVPCReadsFromMetadataStore(t *testing.T) {
	now := time.Unix(200, 0).UTC()
	tx := &fakeMetadataTx{
		row: vpcFakeRow{
			record: ports.NetworkVPCRecord{
				TenantID:  networkStoreTenantID,
				VPCID:     "vpc-restart",
				Name:      "restart-vpc",
				CIDR:      "10.10.0.0/16",
				State:     ports.NetworkResourceAvailable,
				CreatedAt: now,
				UpdatedAt: now,
			},
		},
	}
	store := NewMetadataNetworkStore(fakeMetadataStore{tx: tx})
	if err := store.UpsertVPC(context.Background(), ports.NetworkVPCRecord{
		TenantID:  networkStoreTenantID,
		VPCID:     "vpc-restart",
		Name:      "restart-vpc",
		CIDR:      "10.10.0.0/16",
		State:     ports.NetworkResourceAvailable,
		CreatedAt: now,
		UpdatedAt: now,
	}); err != nil {
		t.Fatalf("UpsertVPC() error = %v", err)
	}
	service := NewLocalNetworkService(WithNetworkResourceStore(store))
	got, err := service.GetVPC(context.Background(), ports.NetworkResourceGetRequest{
		TenantID:   networkStoreTenantID,
		ResourceID: "vpc-restart",
	})
	if err != nil {
		t.Fatalf("GetVPC() error = %v", err)
	}
	if got.Name != "restart-vpc" {
		t.Fatalf("name = %q, want restart-vpc", got.Name)
	}
}

func TestMetadataStorageStoreGetVolumeUsesTenantScopedQuery(t *testing.T) {
	now := time.Unix(300, 0).UTC()
	tx := &fakeMetadataTx{
		row: volumeFakeRow{
			record: ports.StorageVolumeRecord{
				TenantID:     storageStoreTenantID,
				VolumeID:     "vol-read",
				Name:         "read-volume",
				SizeGiB:      10,
				StorageClass: "fast",
				State:        ports.StorageResourceAvailable,
				CreatedAt:    now,
				UpdatedAt:    now,
			},
		},
	}
	store := NewMetadataStorageStore(fakeMetadataStore{tx: tx})
	record, err := store.GetVolume(context.Background(), storageStoreTenantID, "vol-read")
	if err != nil {
		t.Fatalf("GetVolume() error = %v", err)
	}
	if record.Name != "read-volume" {
		t.Fatalf("name = %q, want read-volume", record.Name)
	}
	if !strings.Contains(tx.queryRowSQL, "FROM storage_volumes") {
		t.Fatalf("query = %q, want storage_volumes select", tx.queryRowSQL)
	}
}

func TestLocalStorageServiceGetVolumeReadsFromMetadataStore(t *testing.T) {
	now := time.Unix(300, 0).UTC()
	tx := &fakeMetadataTx{
		row: volumeFakeRow{
			record: ports.StorageVolumeRecord{
				TenantID:     storageStoreTenantID,
				VolumeID:     "vol-restart",
				Name:         "restart-volume",
				SizeGiB:      20,
				StorageClass: "fast",
				State:        ports.StorageResourceAvailable,
				CreatedAt:    now,
				UpdatedAt:    now,
			},
		},
	}
	store := NewMetadataStorageStore(fakeMetadataStore{tx: tx})
	service := NewLocalStorageService(WithStorageResourceStore(store))
	got, err := service.GetVolume(context.Background(), ports.StorageResourceGetRequest{
		TenantID:   storageStoreTenantID,
		ResourceID: "vol-restart",
	})
	if err != nil {
		t.Fatalf("GetVolume() error = %v", err)
	}
	if got.Name != "restart-volume" {
		t.Fatalf("name = %q, want restart-volume", got.Name)
	}
}
