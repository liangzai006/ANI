package runtime

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/kubercloud/ani/pkg/ports"
)

func TestMetadataRegistryStoreUpsertsProject(t *testing.T) {
	tx := &fakeMetadataTx{}
	store := NewMetadataRegistryStore(fakeMetadataStore{tx: tx}, WithRegistryStoreClock(func() time.Time {
		return time.Unix(200, 0).UTC()
	}))
	err := store.UpsertProject(context.Background(), ports.RegistryProjectRecord{
		TenantID:     "00000000-0000-0000-0000-000000000001",
		ProjectID:    "regproj-tenant",
		Name:         "00000000-0000-0000-0000-000000000001",
		Public:       true,
		ProviderMode: "local",
	}, "idem-reg-proj")
	if err != nil {
		t.Fatalf("UpsertProject() error = %v", err)
	}
	if !strings.Contains(tx.sql, "INSERT INTO registry_projects") {
		t.Fatalf("sql = %q, want registry_projects insert", tx.sql)
	}
}

func TestMetadataRegistryStoreListProjectsUsesTenantScopedQuery(t *testing.T) {
	tx := &fakeMetadataTx{
		queryRows: []ports.Row{
			fakeMetadataRow{values: []any{"regproj-tenant", "00000000-0000-0000-0000-000000000001", true, "local", time.Unix(1, 0), time.Unix(2, 0)}},
		},
	}
	store := NewMetadataRegistryStore(fakeMetadataStore{tx: tx})
	records, err := store.ListProjects(context.Background(), "00000000-0000-0000-0000-000000000001")
	if err != nil {
		t.Fatalf("ListProjects() error = %v", err)
	}
	if len(records) != 1 || records[0].ProjectID != "regproj-tenant" {
		t.Fatalf("records = %#v, want one project", records)
	}
	if !strings.Contains(tx.querySQL, "FROM registry_projects") {
		t.Fatalf("querySQL = %q, want registry_projects select", tx.querySQL)
	}
}

func TestMetadataRegistryStoreUpsertsRepositoryPermission(t *testing.T) {
	tx := &fakeMetadataTx{}
	store := NewMetadataRegistryStore(fakeMetadataStore{tx: tx})
	err := store.UpsertRepositoryPermission(context.Background(), ports.RegistryPermissionRecord{
		TenantID:   "00000000-0000-0000-0000-000000000001",
		Project:    "00000000-0000-0000-0000-000000000001",
		Repository: "runtime",
		Subject:    "svc-model",
		Actions:    []ports.RegistryPermissionAction{ports.RegistryPermissionPull},
		State:      ports.RegistryPermissionActive,
		UpdatedAt:  time.Unix(300, 0).UTC(),
	}, "idem-reg-perm")
	if err != nil {
		t.Fatalf("UpsertRepositoryPermission() error = %v", err)
	}
	if !strings.Contains(tx.sql, "INSERT INTO registry_repository_permissions") {
		t.Fatalf("sql = %q, want registry_repository_permissions insert", tx.sql)
	}
}

func TestMetadataRegistryStoreUpsertsPullSecret(t *testing.T) {
	tx := &fakeMetadataTx{}
	store := NewMetadataRegistryStore(fakeMetadataStore{tx: tx})
	err := store.UpsertPullSecret(context.Background(), ports.RegistryPullSecretRecord{
		TenantID:  "00000000-0000-0000-0000-000000000001",
		Project:   "00000000-0000-0000-0000-000000000001",
		Name:      "ani-registry-pull",
		SecretRef: "project/secret",
		Registry:  "registry.local",
		Username:  "robot$user",
		Namespace: "default",
		State:     ports.RegistryPermissionActive,
		CreatedAt: time.Unix(400, 0).UTC(),
	}, "idem-reg-secret")
	if err != nil {
		t.Fatalf("UpsertPullSecret() error = %v", err)
	}
	if !strings.Contains(tx.sql, "INSERT INTO registry_pull_secrets") {
		t.Fatalf("sql = %q, want registry_pull_secrets insert", tx.sql)
	}
}
