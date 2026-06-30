package router

import (
	"context"
	"testing"

	"github.com/kubercloud/ani/pkg/ports"
)

func TestRegistryAPIProjectRepositoryAndArtifactResponses(t *testing.T) {
	api := newRegistryAPI()
	if err := api.service.EnsureProject(context.Background(), "tenant-a"); err != nil {
		t.Fatalf("EnsureProject error = %v", err)
	}

	projects, err := api.service.ListProjects(context.Background(), ports.RegistryProjectListRequest{TenantID: "tenant-a"})
	if err != nil {
		t.Fatalf("ListProjects error = %v", err)
	}
	projectResponse := registryProjectsFromResult(projects)
	if projectResponse.Total != 1 || projectResponse.Items[0].Name != "default" {
		t.Fatalf("project response = %+v, want default project", projectResponse)
	}
	requireLocalCoreDevProfile(t, projectResponse.Items[0].DevProfile, "local-image-registry")

	repositories, err := api.service.ListRepositories(context.Background(), ports.RegistryRepositoryListRequest{
		TenantID: "tenant-a",
		Project:  "default",
	})
	if err != nil {
		t.Fatalf("ListRepositories error = %v", err)
	}
	repositoryResponse := registryRepositoriesFromResult(repositories)
	if repositoryResponse.Total != 1 || repositoryResponse.Items[0].Name != "runtime" {
		t.Fatalf("repository response = %+v, want runtime repository", repositoryResponse)
	}

	artifacts, err := api.service.ListArtifacts(context.Background(), ports.RegistryArtifactListRequest{
		TenantID:   "tenant-a",
		Project:    "default",
		Repository: "runtime",
	})
	if err != nil {
		t.Fatalf("ListArtifacts error = %v", err)
	}
	artifactResponse := registryArtifactsFromResult(artifacts)
	if artifactResponse.Total != 1 || artifactResponse.Items[0].Tags[0] != "latest" {
		t.Fatalf("artifact response = %+v, want latest artifact", artifactResponse)
	}
}

func TestRegistryAPIPermissionAndScanResponses(t *testing.T) {
	api := newRegistryAPI()
	if err := api.service.EnsureProject(context.Background(), "tenant-a"); err != nil {
		t.Fatalf("EnsureProject error = %v", err)
	}

	permission, err := api.service.SetRepositoryPermission(context.Background(), ports.RegistryPermissionRequest{
		TenantID:       "tenant-a",
		Project:        "default",
		Repository:     "runtime",
		IdempotencyKey: "registry-router-permission",
		Subject:        "svc-model",
		Actions:        []ports.RegistryPermissionAction{ports.RegistryPermissionPull},
	})
	if err != nil {
		t.Fatalf("SetRepositoryPermission error = %v", err)
	}
	permissionResponse := registryPermissionFromRecord(permission)
	if permissionResponse.Subject != "svc-model" || permissionResponse.State != "active" {
		t.Fatalf("permission response = %+v, want active svc-model permission", permissionResponse)
	}
	requireLocalCoreDevProfile(t, permissionResponse.DevProfile, "local-image-registry")

	scan, err := api.service.GetScanResult(context.Background(), ports.RegistryScanResultRequest{
		TenantID: "tenant-a",
		Image:    "default/runtime:latest",
	})
	if err != nil {
		t.Fatalf("GetScanResult error = %v", err)
	}
	scanResponse := registryScanResultFromRecord(scan)
	if scanResponse.Status != "complete" || scanResponse.ProviderID != "local-trivy" {
		t.Fatalf("scan response = %+v, want complete local-trivy scan", scanResponse)
	}
	requireLocalCoreDevProfile(t, scanResponse.DevProfile, "local-image-registry")
}

func TestRegistryAPIProjectPullSecretAndScanReportResponses(t *testing.T) {
	api := newRegistryAPI()

	project, err := api.service.CreateProject(context.Background(), ports.RegistryProjectRequest{
		TenantID:       "tenant-a",
		IdempotencyKey: "registry-router-project",
		Name:           "runtime-team",
	})
	if err != nil {
		t.Fatalf("CreateProject error = %v", err)
	}
	projectResponse := registryProjectFromRecord(project)
	if projectResponse.Name != "runtime-team" {
		t.Fatalf("project response = %+v, want runtime-team", projectResponse)
	}
	requireLocalCoreDevProfile(t, projectResponse.DevProfile, "local-image-registry")

	secret, err := api.service.CreatePullSecret(context.Background(), ports.RegistryPullSecretRequest{
		TenantID:       "tenant-a",
		Project:        "runtime-team",
		IdempotencyKey: "registry-router-pull-secret",
		Name:           "ani-registry-pull",
	})
	if err != nil {
		t.Fatalf("CreatePullSecret error = %v", err)
	}
	secretResponse := registryPullSecretFromRecord(secret)
	if secretResponse.SecretRef == "" || secretResponse.State != "active" {
		t.Fatalf("secret response = %+v, want active secret reference", secretResponse)
	}
	requireLocalCoreDevProfile(t, secretResponse.DevProfile, "local-image-registry")

	report, err := api.service.GetProjectScanReport(context.Background(), ports.RegistryProjectScanReportRequest{
		TenantID: "tenant-a",
		Project:  "runtime-team",
	})
	if err != nil {
		t.Fatalf("GetProjectScanReport error = %v", err)
	}
	reportResponse := registryProjectScanReportFromRecord(report)
	if reportResponse.Status != "complete" || reportResponse.ArtifactsTotal != 1 {
		t.Fatalf("report response = %+v, want complete one-artifact report", reportResponse)
	}
	requireLocalCoreDevProfile(t, reportResponse.DevProfile, "local-image-registry")
}
