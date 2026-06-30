package registry

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/kubercloud/ani/pkg/ports"
)

type recordingRegistryStore struct {
	projects    []ports.RegistryProjectRecord
	permissions []ports.RegistryPermissionRecord
	secrets     []ports.RegistryPullSecretRecord
}

func (s *recordingRegistryStore) UpsertProject(_ context.Context, record ports.RegistryProjectRecord, _ string) error {
	s.projects = append(s.projects, record)
	return nil
}

func (s *recordingRegistryStore) ListProjects(_ context.Context, tenantID string) ([]ports.RegistryProjectRecord, error) {
	items := make([]ports.RegistryProjectRecord, 0)
	for _, project := range s.projects {
		if project.TenantID == tenantID {
			items = append(items, project)
		}
	}
	return items, nil
}

func (s *recordingRegistryStore) GetProjectByIdempotency(_ context.Context, tenantID, idempotencyKey string) (ports.RegistryProjectRecord, error) {
	return ports.RegistryProjectRecord{}, ports.ErrNotFound
}

func (s *recordingRegistryStore) UpsertRepositoryPermission(_ context.Context, record ports.RegistryPermissionRecord, _ string) error {
	s.permissions = append(s.permissions, record)
	return nil
}

func (s *recordingRegistryStore) GetPermissionByIdempotency(_ context.Context, tenantID, idempotencyKey string) (ports.RegistryPermissionRecord, error) {
	return ports.RegistryPermissionRecord{}, ports.ErrNotFound
}

func (s *recordingRegistryStore) GetRepositoryPermission(_ context.Context, tenantID, project, repository, subject string) (ports.RegistryPermissionRecord, error) {
	for _, permission := range s.permissions {
		if permission.TenantID == tenantID && permission.Project == project && permission.Repository == repository && permission.Subject == subject {
			return permission, nil
		}
	}
	return ports.RegistryPermissionRecord{}, ports.ErrNotFound
}

func (s *recordingRegistryStore) UpsertPullSecret(_ context.Context, record ports.RegistryPullSecretRecord, _ string) error {
	s.secrets = append(s.secrets, record)
	return nil
}

func (s *recordingRegistryStore) GetPullSecretByIdempotency(_ context.Context, tenantID, idempotencyKey string) (ports.RegistryPullSecretRecord, error) {
	return ports.RegistryPullSecretRecord{}, ports.ErrNotFound
}

func TestPersistingImageRegistryCreateProjectPersistsMetadata(t *testing.T) {
	store := &recordingRegistryStore{}
	tenantID := "00000000-0000-0000-0000-000000000001"
	service := NewPersistingImageRegistry(NewLocalImageRegistry(), store, "local")
	project, err := service.CreateProject(context.Background(), ports.RegistryProjectRequest{
		TenantID:       tenantID,
		IdempotencyKey: "idem-p5-project",
		Name:           "my-backend",
		Public:         true,
	})
	if err != nil {
		t.Fatalf("CreateProject() error = %v", err)
	}
	if len(store.projects) != 1 {
		t.Fatalf("projects persisted = %d, want 1", len(store.projects))
	}
	if store.projects[0].ProjectID != project.ID || store.projects[0].ProviderMode != "local" {
		t.Fatalf("stored project = %#v, want provider local and id %q", store.projects[0], project.ID)
	}
}

func TestPersistingImageRegistryListProjectsReadsMetadataStore(t *testing.T) {
	tenantID := "00000000-0000-0000-0000-000000000001"
	store := &recordingRegistryStore{
		projects: []ports.RegistryProjectRecord{{
			TenantID:     tenantID,
			ProjectID:    "regproj-persisted",
			Name:         tenantID,
			Public:       false,
			ProviderMode: "harbor",
			CreatedAt:    time.Unix(100, 0).UTC(),
		}},
	}
	service := NewPersistingImageRegistry(NewLocalImageRegistry(), store, "harbor")
	result, err := service.ListProjects(context.Background(), ports.RegistryProjectListRequest{TenantID: tenantID})
	if err != nil {
		t.Fatalf("ListProjects() error = %v", err)
	}
	if len(result.Items) != 1 || result.Items[0].ID != "regproj-persisted" {
		t.Fatalf("items = %#v, want persisted project", result.Items)
	}
	if !strings.Contains(result.DevProfile.Provider, "harbor") {
		t.Fatalf("dev profile = %#v, want harbor provider", result.DevProfile)
	}
}

func TestPersistingImageRegistrySetPermissionPersistsMetadata(t *testing.T) {
	store := &recordingRegistryStore{}
	tenantID := "00000000-0000-0000-0000-000000000001"
	service := NewPersistingImageRegistry(NewLocalImageRegistry(), store, "local")
	_, err := service.SetRepositoryPermission(context.Background(), ports.RegistryPermissionRequest{
		TenantID:       tenantID,
		Project:        tenantID,
		Repository:     "runtime",
		IdempotencyKey: "idem-p5-perm",
		Subject:        "svc-model",
		Actions:        []ports.RegistryPermissionAction{ports.RegistryPermissionPull},
	})
	if err != nil {
		t.Fatalf("SetRepositoryPermission() error = %v", err)
	}
	if len(store.permissions) != 1 || store.permissions[0].Subject != "svc-model" {
		t.Fatalf("permissions = %#v, want one svc-model permission", store.permissions)
	}
}
