package runtime

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/kubercloud/ani/pkg/ports"
)

const encryptionKeyStoreTenantID = "00000000-0000-0000-0000-000000000001"

func TestMetadataEncryptionKeyStoreUpsertsKey(t *testing.T) {
	tx := &fakeMetadataTx{}
	store := NewMetadataEncryptionKeyStore(fakeMetadataStore{tx: tx}, WithEncryptionKeyStoreClock(func() time.Time {
		return time.Unix(200, 0).UTC()
	}))
	err := store.UpsertEncryptionKey(context.Background(), ports.EncryptionKeyRecord{
		TenantID:  encryptionKeyStoreTenantID,
		KeyID:     "ekey-test",
		Name:      "model-seal",
		Algorithm: "SM4",
		State:     "active",
		Provider:  "local",
		CreatedAt: 200,
		UpdatedAt: 200,
	}, "idem-encryption-key")
	if err != nil {
		t.Fatalf("UpsertEncryptionKey() error = %v", err)
	}
	if !strings.Contains(tx.sql, "INSERT INTO encryption_keys") {
		t.Fatalf("sql = %q, want encryption_keys insert", tx.sql)
	}
}

func TestMetadataEncryptionKeyStoreListKeysUsesTenantScopedQuery(t *testing.T) {
	tx := &fakeMetadataTx{
		queryRows: []ports.Row{
			encryptionKeyFakeRow{record: ports.EncryptionKeyRecord{
				TenantID:  encryptionKeyStoreTenantID,
				KeyID:     "ekey-list",
				Name:      "listed-key",
				Algorithm: "SM4",
				State:     "active",
				Provider:  "local",
				CreatedAt: 1,
				UpdatedAt: 2,
			}},
		},
	}
	store := NewMetadataEncryptionKeyStore(fakeMetadataStore{tx: tx})
	records, err := store.ListEncryptionKeys(context.Background(), encryptionKeyStoreTenantID)
	if err != nil {
		t.Fatalf("ListEncryptionKeys() error = %v", err)
	}
	if len(records) != 1 || records[0].KeyID != "ekey-list" {
		t.Fatalf("records = %#v, want one encryption key", records)
	}
	if !strings.Contains(tx.querySQL, "FROM encryption_keys") {
		t.Fatalf("querySQL = %q, want encryption_keys select", tx.querySQL)
	}
}

func TestLocalEncryptionServiceGetKeyReadsFromMetadataStore(t *testing.T) {
	tx := &fakeMetadataTx{
		row: encryptionKeyFakeRow{record: ports.EncryptionKeyRecord{
			TenantID:  encryptionKeyStoreTenantID,
			KeyID:     "ekey-restart",
			Name:      "restart-key",
			Algorithm: "SM4",
			State:     "active",
			Provider:  "local",
			CreatedAt: 300,
			UpdatedAt: 300,
		}},
	}
	store := NewMetadataEncryptionKeyStore(fakeMetadataStore{tx: tx})
	service := NewLocalEncryptionService(WithEncryptionResourceStore(store))
	got, err := service.GetKey(context.Background(), ports.EncryptionKeyGetRequest{
		TenantID: encryptionKeyStoreTenantID,
		KeyID:    "ekey-restart",
	})
	if err != nil {
		t.Fatalf("GetKey() error = %v", err)
	}
	if got.Name != "restart-key" {
		t.Fatalf("name = %q, want restart-key", got.Name)
	}
}

func TestLocalEncryptionServiceListKeysReadsFromMetadataStore(t *testing.T) {
	tx := &fakeMetadataTx{
		queryRows: []ports.Row{
			encryptionKeyFakeRow{record: ports.EncryptionKeyRecord{
				TenantID:  encryptionKeyStoreTenantID,
				KeyID:     "ekey-list-local",
				Name:      "listed-key",
				Algorithm: "SM4",
				State:     "active",
				Provider:  "local",
				CreatedAt: 100,
				UpdatedAt: 100,
			}},
		},
	}
	store := NewMetadataEncryptionKeyStore(fakeMetadataStore{tx: tx})
	service := NewLocalEncryptionService(WithEncryptionResourceStore(store))
	records, err := service.ListKeys(context.Background(), ports.EncryptionKeyListRequest{TenantID: encryptionKeyStoreTenantID})
	if err != nil {
		t.Fatalf("ListKeys() error = %v", err)
	}
	if len(records) != 1 || records[0].KeyID != "ekey-list-local" {
		t.Fatalf("records = %#v, want one encryption key", records)
	}
}

type encryptionKeyFakeRow struct {
	record ports.EncryptionKeyRecord
}

func (r encryptionKeyFakeRow) Scan(dest ...any) error {
	refsJSON := []byte("[]")
	createdAt := time.Unix(r.record.CreatedAt, 0).UTC()
	updatedAt := time.Unix(r.record.UpdatedAt, 0).UTC()
	*dest[0].(*string) = r.record.KeyID
	*dest[1].(*string) = r.record.Name
	*dest[2].(*string) = r.record.Algorithm
	*dest[3].(*string) = r.record.State
	*dest[4].(*string) = r.record.Provider
	*dest[5].(*bool) = r.record.RealProvider
	*dest[6].(*[]byte) = refsJSON
	*dest[7].(*time.Time) = createdAt
	*dest[8].(*time.Time) = updatedAt
	return nil
}
