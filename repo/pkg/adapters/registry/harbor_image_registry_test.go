package registry

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/kubercloud/ani/pkg/ports"
)

func newHarborTestRegistry(t *testing.T, handler http.HandlerFunc) (*HarborImageRegistry, *httptest.Server) {
	t.Helper()
	server := httptest.NewServer(handler)
	t.Cleanup(server.Close)
	registry, err := NewHarborImageRegistry(HarborImageRegistryConfig{
		Endpoint: server.URL,
		Username: "robot",
		Password: "secret",
		Now:      func() time.Time { return time.Unix(4200, 0).UTC() },
	})
	if err != nil {
		t.Fatalf("NewHarborImageRegistry() error = %v", err)
	}
	return registry, server
}

func TestHarborImageRegistryRequiresCredentials(t *testing.T) {
	if _, err := NewHarborImageRegistry(HarborImageRegistryConfig{Endpoint: "http://harbor.example"}); err == nil {
		t.Fatal("NewHarborImageRegistry() error = nil, want missing credential error")
	}
}

func TestHarborImageRegistryCreateProjectUsesRealAPI(t *testing.T) {
	harborName := harborProviderProjectName("tenant-a", "my-app")
	var sawBasicAuth bool
	var createCalls int
	registry, _ := newHarborTestRegistry(t, func(w http.ResponseWriter, r *http.Request) {
		if user, pass, ok := r.BasicAuth(); ok && user == "robot" && pass == "secret" {
			sawBasicAuth = true
		}
		switch {
		case r.Method == http.MethodPost && r.URL.Path == "/api/v2.0/projects":
			createCalls++
			w.WriteHeader(http.StatusCreated)
		case r.Method == http.MethodGet && r.URL.Path == "/api/v2.0/projects/"+harborName:
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"project_id":7,"name":"` + harborName + `","metadata":{"public":"false"},"creation_time":"2026-06-20T10:00:00Z"}`))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	})

	project, err := registry.CreateProject(context.Background(), ports.RegistryProjectRequest{
		TenantID:       "tenant-a",
		IdempotencyKey: "registry-project-a",
		Name:           "my-app",
	})
	if err != nil {
		t.Fatalf("CreateProject() error = %v", err)
	}
	if !sawBasicAuth {
		t.Fatal("Harbor request did not carry basic auth credentials")
	}
	if createCalls != 1 {
		t.Fatalf("create calls = %d, want 1", createCalls)
	}
	if project.ID != "harbor-7" || project.Name != "my-app" {
		t.Fatalf("project = %+v, want harbor-backed my-app project", project)
	}
	if !project.DevProfile.RealProvider || project.DevProfile.Provider != "harbor" {
		t.Fatalf("dev profile = %+v, want real harbor provider marker", project.DevProfile)
	}
}

func TestHarborImageRegistryCreateProjectTreatsConflictAsSuccess(t *testing.T) {
	harborName := harborProviderProjectName("tenant-a", "my-app")
	registry, _ := newHarborTestRegistry(t, func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodPost && r.URL.Path == "/api/v2.0/projects":
			w.WriteHeader(http.StatusConflict)
		case r.Method == http.MethodGet && r.URL.Path == "/api/v2.0/projects/"+harborName:
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"project_id":7,"name":"` + harborName + `","metadata":{"public":"false"}}`))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	})

	if _, err := registry.CreateProject(context.Background(), ports.RegistryProjectRequest{
		TenantID:       "tenant-a",
		IdempotencyKey: "registry-project-a",
		Name:           "my-app",
	}); err != nil {
		t.Fatalf("CreateProject() error = %v, want conflict treated as success", err)
	}
}

func TestHarborImageRegistryListsRepositoriesAndArtifacts(t *testing.T) {
	harborName := harborProviderProjectName("tenant-a", "my-app")
	registry, _ := newHarborTestRegistry(t, func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/api/v2.0/projects/"+harborName+"/repositories":
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`[{"name":"` + harborName + `/runtime","artifact_count":2,"pull_count":5}]`))
		case strings.Contains(r.URL.Path, "/repositories/runtime/artifacts"):
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`[{"digest":"sha256:abc","size":1234,"manifest_media_type":"application/vnd.oci.image.manifest.v1+json","push_time":"2026-06-20T11:00:00Z","tags":[{"name":"latest"}],"scan_overview":{"application/vnd.security.vulnerability.report; version=1.1":{"report_id":"r-1","scan_status":"Success","summary":{"summary":{"Critical":1,"High":2,"Medium":3,"Low":4}}}}}]`))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	})

	repositories, err := registry.ListRepositories(context.Background(), ports.RegistryRepositoryListRequest{TenantID: "tenant-a", Project: "my-app"})
	if err != nil {
		t.Fatalf("ListRepositories() error = %v", err)
	}
	if len(repositories.Items) != 1 || repositories.Items[0].Name != "runtime" || repositories.Items[0].Project != "my-app" {
		t.Fatalf("repositories = %+v, want short-named runtime repository", repositories.Items)
	}

	artifacts, err := registry.ListArtifacts(context.Background(), ports.RegistryArtifactListRequest{TenantID: "tenant-a", Project: "my-app", Repository: "runtime"})
	if err != nil {
		t.Fatalf("ListArtifacts() error = %v", err)
	}
	if len(artifacts.Items) != 1 {
		t.Fatalf("artifacts = %+v, want one artifact", artifacts.Items)
	}
	artifact := artifacts.Items[0]
	if artifact.Digest != "sha256:abc" || artifact.Tags[0] != "latest" || artifact.SizeBytes != 1234 {
		t.Fatalf("artifact = %+v, want harbor artifact fields", artifact)
	}
	if artifact.ScanStatus.Status != ports.RegistryScanComplete || artifact.ScanStatus.Critical != 1 || artifact.ScanStatus.High != 2 {
		t.Fatalf("scan status = %+v, want complete severity counts", artifact.ScanStatus)
	}
	if !artifact.DevProfile.RealProvider {
		t.Fatalf("dev profile = %+v, want real provider marker", artifact.DevProfile)
	}
}

func TestHarborImageRegistryGetScanResultParsesImageReference(t *testing.T) {
	harborName := harborProviderProjectName("tenant-a", "my-app")
	var requestedPath string
	registry, _ := newHarborTestRegistry(t, func(w http.ResponseWriter, r *http.Request) {
		requestedPath = r.URL.EscapedPath()
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"digest":"sha256:abc","scan_overview":{"x":{"report_id":"r-9","scan_status":"Success","summary":{"summary":{"Critical":0,"High":1,"Medium":0,"Low":2}}}}}`))
	})

	result, err := registry.GetScanResult(context.Background(), ports.RegistryScanResultRequest{TenantID: "tenant-a", Image: "my-app/runtime:latest"})
	if err != nil {
		t.Fatalf("GetScanResult() error = %v", err)
	}
	if !strings.Contains(requestedPath, "/projects/"+harborName+"/repositories/runtime/artifacts/latest") {
		t.Fatalf("requested path = %q, want artifact reference path for mapped harbor project", requestedPath)
	}
	if result.Status != ports.RegistryScanComplete || result.High != 1 || result.Low != 2 {
		t.Fatalf("scan result = %+v, want parsed harbor scan overview", result)
	}
	if result.ProviderID != harborProviderID {
		t.Fatalf("provider id = %q, want %q", result.ProviderID, harborProviderID)
	}
}

func TestHarborImageRegistryPullSecretMapsRobotState(t *testing.T) {
	harborName := harborProviderProjectName("tenant-a", "my-app")
	statuses := []int{http.StatusCreated, http.StatusConflict}
	var index int
	registry, _ := newHarborTestRegistry(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost && r.URL.Path == "/api/v2.0/robots" {
			status := statuses[index]
			if index < len(statuses)-1 {
				index++
			}
			w.WriteHeader(status)
			if status == http.StatusCreated {
				_, _ = w.Write([]byte(`{"id":1,"name":"robot$` + harborName + `+ani-registry-pull","secret":"harbor-robot-secret"}`))
			}
			return
		}
		w.WriteHeader(http.StatusNotFound)
	})

	first, err := registry.CreatePullSecret(context.Background(), ports.RegistryPullSecretRequest{
		TenantID:       "tenant-a",
		Project:        "my-app",
		IdempotencyKey: "pull-a",
		Name:           "ani-registry-pull",
		Namespace:      "ani-tenant-a",
	})
	if err != nil {
		t.Fatalf("CreatePullSecret(first) error = %v", err)
	}
	if first.State != ports.RegistryPermissionActive || first.SecretRef != "my-app/ani-registry-pull" {
		t.Fatalf("first secret = %+v, want active secret reference", first)
	}
	if !strings.HasPrefix(first.Username, "robot$"+harborName+"+") {
		t.Fatalf("username = %q, want harbor robot account name", first.Username)
	}

	second, err := registry.CreatePullSecret(context.Background(), ports.RegistryPullSecretRequest{
		TenantID:       "tenant-a",
		Project:        "my-app",
		IdempotencyKey: "pull-a",
		Name:           "ani-registry-pull",
	})
	if err != nil {
		t.Fatalf("CreatePullSecret(second) error = %v", err)
	}
	if second.State != ports.RegistryPermissionDuplicate {
		t.Fatalf("second state = %q, want duplicate from harbor conflict", second.State)
	}
}

func TestHarborImageRegistrySetPermissionScopesRobotAccess(t *testing.T) {
	var sawPullAndPush bool
	registry, _ := newHarborTestRegistry(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost && r.URL.Path == "/api/v2.0/robots" {
			buf := make([]byte, r.ContentLength)
			_, _ = r.Body.Read(buf)
			body := string(buf)
			if strings.Contains(body, `"action":"pull"`) && strings.Contains(body, `"action":"push"`) {
				sawPullAndPush = true
			}
			w.WriteHeader(http.StatusCreated)
			return
		}
		w.WriteHeader(http.StatusNotFound)
	})

	permission, err := registry.SetRepositoryPermission(context.Background(), ports.RegistryPermissionRequest{
		TenantID:       "tenant-a",
		Project:        "my-app",
		Repository:     "runtime",
		IdempotencyKey: "perm-a",
		Subject:        "svc-model",
		Actions:        []ports.RegistryPermissionAction{ports.RegistryPermissionPull, ports.RegistryPermissionPush},
	})
	if err != nil {
		t.Fatalf("SetRepositoryPermission() error = %v", err)
	}
	if !sawPullAndPush {
		t.Fatal("harbor robot access did not include requested pull/push actions")
	}
	if permission.State != ports.RegistryPermissionActive || permission.Subject != "svc-model" {
		t.Fatalf("permission = %+v, want active scoped permission", permission)
	}
}

func TestHarborImageRegistryListProjectsFiltersTenantScopedHarborProjects(t *testing.T) {
	harborName := harborProviderProjectName("tenant-a", "my-app")
	registry, _ := newHarborTestRegistry(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet && r.URL.Path == "/api/v2.0/projects" {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`[{"project_id":7,"name":"` + harborName + `","metadata":{"public":"false"},"creation_time":"2026-06-20T10:00:00Z"},{"project_id":8,"name":"ani-other-tenant-b-app","metadata":{"public":"false"}}]`))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	})

	result, err := registry.ListProjects(context.Background(), ports.RegistryProjectListRequest{TenantID: "tenant-a"})
	if err != nil {
		t.Fatalf("ListProjects() error = %v", err)
	}
	if len(result.Items) != 1 || result.Items[0].Name != "my-app" {
		t.Fatalf("items = %+v, want tenant-a mapped project only", result.Items)
	}
}
