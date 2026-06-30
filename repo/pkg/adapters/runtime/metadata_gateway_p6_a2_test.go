package runtime

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/kubercloud/ani/pkg/ports"
)

const secretStoreTenantID = "00000000-0000-0000-0000-000000000001"

func TestMetadataSecretStoreUpsertsSecret(t *testing.T) {
	tx := &fakeMetadataTx{}
	store := NewMetadataSecretStore(fakeMetadataStore{tx: tx}, WithSecretStoreClock(func() time.Time {
		return time.Unix(200, 0).UTC()
	}))
	err := store.UpsertSecret(context.Background(), ports.SecretRecord{
		TenantID:  secretStoreTenantID,
		SecretID:  "sec-test",
		Name:      "db-password",
		Type:      "opaque",
		Keys:      []string{"password", "username"},
		State:     "active",
		Provider:  "local",
		CreatedAt: 200,
		UpdatedAt: 200,
	}, "idem-secret")
	if err != nil {
		t.Fatalf("UpsertSecret() error = %v", err)
	}
	if !strings.Contains(tx.sql, "INSERT INTO secrets") {
		t.Fatalf("sql = %q, want secrets insert", tx.sql)
	}
}

func TestMetadataSecretStoreListSecretsUsesTenantScopedQuery(t *testing.T) {
	tx := &fakeMetadataTx{
		queryRows: []ports.Row{
			secretFakeRow{record: ports.SecretRecord{
				TenantID:  secretStoreTenantID,
				SecretID:  "sec-list",
				Name:      "api-token",
				Type:      "opaque",
				Keys:      []string{"token"},
				State:     "active",
				Provider:  "local",
				CreatedAt: 1,
				UpdatedAt: 2,
			}},
		},
	}
	store := NewMetadataSecretStore(fakeMetadataStore{tx: tx})
	records, err := store.ListSecrets(context.Background(), secretStoreTenantID)
	if err != nil {
		t.Fatalf("ListSecrets() error = %v", err)
	}
	if len(records) != 1 || records[0].SecretID != "sec-list" {
		t.Fatalf("records = %#v, want one secret", records)
	}
	if !strings.Contains(tx.querySQL, "FROM secrets") {
		t.Fatalf("querySQL = %q, want secrets select", tx.querySQL)
	}
}

func TestMetadataSecretStoreUpsertsSecretBinding(t *testing.T) {
	tx := &fakeMetadataTx{}
	store := NewMetadataSecretStore(fakeMetadataStore{tx: tx})
	err := store.UpsertSecretBinding(context.Background(), ports.SecretBindingRecord{
		BindingID:  "sbind-test",
		SecretID:   "sec-test",
		TenantID:   secretStoreTenantID,
		TargetType: "instance",
		TargetID:   "inst-1",
		MountPath:  "/etc/secret",
		State:      "bound",
		CreatedAt:  300,
	})
	if err != nil {
		t.Fatalf("UpsertSecretBinding() error = %v", err)
	}
	if !strings.Contains(tx.sql, "INSERT INTO secret_bindings") {
		t.Fatalf("sql = %q, want secret_bindings insert", tx.sql)
	}
}

func TestLocalSecretServiceGetSecretReadsFromMetadataStore(t *testing.T) {
	tx := &fakeMetadataTx{
		row: secretFakeRow{record: ports.SecretRecord{
			TenantID:  secretStoreTenantID,
			SecretID:  "sec-restart",
			Name:      "restart-secret",
			Type:      "opaque",
			Keys:      []string{"token"},
			State:     "active",
			Provider:  "local",
			CreatedAt: 300,
			UpdatedAt: 300,
		}},
	}
	store := NewMetadataSecretStore(fakeMetadataStore{tx: tx})
	service := NewLocalSecretService(WithSecretResourceStore(store))
	got, err := service.GetSecret(context.Background(), ports.SecretGetRequest{
		TenantID: secretStoreTenantID,
		SecretID: "sec-restart",
	})
	if err != nil {
		t.Fatalf("GetSecret() error = %v", err)
	}
	if got.Name != "restart-secret" {
		t.Fatalf("name = %q, want restart-secret", got.Name)
	}
}

func TestLocalSecretServiceListSecretsReadsFromMetadataStore(t *testing.T) {
	tx := &fakeMetadataTx{
		queryRows: []ports.Row{
			secretFakeRow{record: ports.SecretRecord{
				TenantID:  secretStoreTenantID,
				SecretID:  "sec-list-local",
				Name:      "listed-secret",
				Type:      "opaque",
				Keys:      []string{"key"},
				State:     "active",
				Provider:  "local",
				CreatedAt: 100,
				UpdatedAt: 100,
			}},
		},
	}
	store := NewMetadataSecretStore(fakeMetadataStore{tx: tx})
	service := NewLocalSecretService(WithSecretResourceStore(store))
	records, err := service.ListSecrets(context.Background(), ports.SecretListRequest{TenantID: secretStoreTenantID})
	if err != nil {
		t.Fatalf("ListSecrets() error = %v", err)
	}
	if len(records) != 1 || records[0].SecretID != "sec-list-local" {
		t.Fatalf("records = %#v, want one secret", records)
	}
}

type secretFakeRow struct {
	record ports.SecretRecord
}

func (r secretFakeRow) Scan(dest ...any) error {
	keysJSON := []byte(`["token"]`)
	if len(r.record.Keys) > 0 {
		keysJSON = []byte(`["` + r.record.Keys[0] + `"]`)
	}
	refsJSON := []byte("[]")
	createdAt := time.Unix(r.record.CreatedAt, 0).UTC()
	updatedAt := time.Unix(r.record.UpdatedAt, 0).UTC()
	*dest[0].(*string) = r.record.SecretID
	*dest[1].(*string) = r.record.Name
	*dest[2].(*string) = r.record.Type
	*dest[3].(*[]byte) = keysJSON
	*dest[4].(*string) = r.record.State
	*dest[5].(*string) = r.record.Provider
	*dest[6].(*bool) = r.record.RealProvider
	*dest[7].(*[]byte) = refsJSON
	*dest[8].(*time.Time) = createdAt
	*dest[9].(*time.Time) = updatedAt
	return nil
}
