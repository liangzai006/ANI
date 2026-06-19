package runtime

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/kubercloud/ani/pkg/ports"
)

func TestKubernetesStorageProviderAdapterUsesServerSideDryRun(t *testing.T) {
	client := &fakeKubernetesStorageProviderClient{}
	manifests := renderedStorageVolume(t)
	adapter := NewKubernetesStorageProviderAdapter(client, WithKubernetesStorageProviderClock(func() time.Time {
		return time.Unix(1500, 0)
	}))

	result, err := adapter.DryRun(context.Background(), ports.StorageProviderDryRunRequest{
		TenantID:        "tenant-a",
		UserID:          "user-a",
		ResourceKind:    "volume",
		ResourceID:      "vol-data",
		Operation:       ports.StorageProviderOperationCreate,
		Manifests:       manifests,
		PermissionProof: "rbac:scope:volumes:create",
	})
	if err != nil {
		t.Fatalf("DryRun() error = %v", err)
	}
	if !result.Accepted || !strings.Contains(result.Reason, "dryRun=All") {
		t.Fatalf("result = %#v, want accepted dryRun=All", result)
	}
	if len(result.ResourceRefs) != 1 || result.ResourceRefs[0] != "kubernetes/PersistentVolumeClaim/vol-vol-data" {
		t.Fatalf("ResourceRefs = %#v, want PVC ref", result.ResourceRefs)
	}
	if client.dryRuns != 1 {
		t.Fatalf("dryRuns = %d, want 1", client.dryRuns)
	}
}

func TestKubernetesStorageProviderAdapterApplyFailsClosed(t *testing.T) {
	client := &fakeKubernetesStorageProviderClient{}
	manifests := renderedStorageVolume(t)
	result, err := NewKubernetesStorageProviderAdapter(client).Apply(context.Background(), ports.StorageProviderApplyRequest{
		TenantID:        "tenant-a",
		UserID:          "user-a",
		ResourceKind:    "volume",
		ResourceID:      "vol-data",
		Operation:       ports.StorageProviderOperationCreate,
		Manifests:       manifests,
		PermissionProof: "rbac:scope:volumes:create",
		DryRunResult: ports.StorageProviderDryRunResult{
			Accepted:      true,
			Provider:      "kubernetes",
			ManifestCount: len(manifests),
			ResourceRefs:  []string{"kubernetes/PersistentVolumeClaim/vol-vol-data"},
		},
	})
	if err != nil {
		t.Fatalf("Apply() error = %v", err)
	}
	if result.Applied {
		t.Fatalf("Applied = true, want false")
	}
	if client.applies != 0 {
		t.Fatalf("applies = %d, want 0", client.applies)
	}
}

func TestKubernetesStorageProviderAdapterAppliesWhenEnabled(t *testing.T) {
	client := &fakeKubernetesStorageProviderClient{}
	manifests := renderedStorageFilesystem(t)
	result, err := NewKubernetesStorageProviderAdapter(
		client,
		WithKubernetesStorageProviderApplyEnabled(true),
		WithKubernetesStorageProviderClock(func() time.Time { return time.Unix(1600, 0) }),
	).Apply(context.Background(), ports.StorageProviderApplyRequest{
		TenantID:        "tenant-a",
		UserID:          "user-a",
		ResourceKind:    "filesystem",
		ResourceID:      "fs-shared",
		Operation:       ports.StorageProviderOperationCreate,
		Manifests:       manifests,
		PermissionProof: "rbac:scope:filesystems:create",
		DryRunResult: ports.StorageProviderDryRunResult{
			Accepted:      true,
			Provider:      "kubernetes",
			ManifestCount: len(manifests),
			ResourceRefs:  []string{"kubernetes/PersistentVolumeClaim/fs-fs-shared"},
		},
	})
	if err != nil {
		t.Fatalf("Apply() error = %v", err)
	}
	if !result.Applied {
		t.Fatalf("Applied = false, reason = %s", result.Reason)
	}
	if len(result.ResourceRefs) != 1 || result.ResourceRefs[0] != "kubernetes/PersistentVolumeClaim/fs-fs-shared" {
		t.Fatalf("ResourceRefs = %#v, want PVC ref", result.ResourceRefs)
	}
	if client.applies != 1 {
		t.Fatalf("applies = %d, want 1", client.applies)
	}
}

func TestKubernetesStorageProviderAdapterRejectsObjectStoreManifest(t *testing.T) {
	manifests, err := NewKubernetesStorageRenderer().RenderObject(context.Background(), ports.StorageObjectRecord{
		TenantID:  "tenant-a",
		ObjectID:  "obj-model",
		Bucket:    "models",
		Key:       "model.bin",
		SizeBytes: 1024,
		State:     ports.StorageResourceAvailable,
	})
	if err != nil {
		t.Fatalf("RenderObject() error = %v", err)
	}
	_, err = NewKubernetesStorageProviderAdapter(&fakeKubernetesStorageProviderClient{}).DryRun(context.Background(), ports.StorageProviderDryRunRequest{
		TenantID:        "tenant-a",
		UserID:          "user-a",
		ResourceKind:    "object",
		ResourceID:      "obj-model",
		Operation:       ports.StorageProviderOperationCreate,
		Manifests:       manifests,
		PermissionProof: "rbac:scope:objects:create",
	})
	if err == nil || !strings.Contains(err.Error(), "Kubernetes PVC manifests only") {
		t.Fatalf("DryRun(ObjectMetadata) error = %v, want unsupported objectstore path", err)
	}
}

func TestKubernetesStorageProviderAdapterDryRunsSnapshotAndMountTargetManifests(t *testing.T) {
	client := &fakeKubernetesStorageProviderClient{}
	renderer := NewKubernetesStorageRenderer()
	snapshotManifests, err := renderer.RenderVolumeSnapshot(context.Background(), ports.VolumeSnapshotRecord{
		TenantID:   "tenant-a",
		SnapshotID: "snap-daily",
		VolumeID:   "vol-data",
		Name:       "daily",
		Status:     ports.VolumeSnapshotCreating,
		SizeBytes:  8 * 1024 * 1024 * 1024,
	})
	if err != nil {
		t.Fatalf("RenderVolumeSnapshot() error = %v", err)
	}
	mountTargetManifests, err := renderer.RenderFilesystemMountTarget(context.Background(), ports.FilesystemMountTargetRecord{
		TenantID:      "tenant-a",
		MountTargetID: "mt-shared",
		FilesystemID:  "fs-shared",
		SubnetID:      "subnet-a",
		IPAddress:     "10.0.1.25",
		Status:        ports.MountTargetCreating,
	})
	if err != nil {
		t.Fatalf("RenderFilesystemMountTarget() error = %v", err)
	}

	snapshotResult, err := NewKubernetesStorageProviderAdapter(client).DryRun(context.Background(), ports.StorageProviderDryRunRequest{
		TenantID:        "tenant-a",
		UserID:          "user-a",
		ResourceKind:    "volume_snapshot",
		ResourceID:      "snap-daily",
		Operation:       ports.StorageProviderOperationCreate,
		Manifests:       snapshotManifests,
		PermissionProof: "rbac:scope:volumes:create",
	})
	if err != nil {
		t.Fatalf("DryRun(snapshot) error = %v", err)
	}
	if !snapshotResult.Accepted || snapshotResult.ResourceRefs[0] != "kubernetes/VolumeSnapshot/snap-snap-daily" {
		t.Fatalf("snapshot dry-run result = %#v, want accepted VolumeSnapshot ref", snapshotResult)
	}

	mountTargetResult, err := NewKubernetesStorageProviderAdapter(client).DryRun(context.Background(), ports.StorageProviderDryRunRequest{
		TenantID:        "tenant-a",
		UserID:          "user-a",
		ResourceKind:    "filesystem_mount_target",
		ResourceID:      "mt-shared",
		Operation:       ports.StorageProviderOperationCreate,
		Manifests:       mountTargetManifests,
		PermissionProof: "rbac:scope:filesystems:read",
	})
	if err != nil {
		t.Fatalf("DryRun(mount target) error = %v", err)
	}
	if !mountTargetResult.Accepted || mountTargetResult.ResourceRefs[0] != "kubernetes/Service/mt-mt-shared" {
		t.Fatalf("mount target dry-run result = %#v, want accepted Service ref", mountTargetResult)
	}
	if client.dryRuns != 2 {
		t.Fatalf("dryRuns = %d, want 2", client.dryRuns)
	}
}

func TestKubernetesStorageProviderAdapterObservesStorageStatus(t *testing.T) {
	client := &fakeKubernetesStorageProviderClient{
		status: ports.StorageProviderStatusResult{
			TenantID:     "tenant-a",
			ResourceKind: "volume",
			ResourceID:   "vol-data",
			Provider:     "kubernetes",
			ResourceRefs: []string{"kubernetes/PersistentVolumeClaim/vol-vol-data"},
			State:        ports.StorageResourceAvailable,
			Reason:       "observed Kubernetes PVC phase Bound",
		},
	}
	result, err := NewKubernetesStorageProviderAdapter(
		client,
		WithKubernetesStorageProviderClock(func() time.Time { return time.Unix(1700, 0) }),
	).Observe(context.Background(), ports.StorageProviderStatusRequest{
		TenantID:        "tenant-a",
		UserID:          "user-a",
		ResourceKind:    "volume",
		ResourceID:      "vol-data",
		PermissionProof: "rbac:scope:volumes:read",
		ApplyResult: ports.StorageProviderApplyResult{
			Applied:      true,
			Provider:     "kubernetes",
			ResourceRefs: []string{"kubernetes/PersistentVolumeClaim/vol-vol-data"},
		},
	})
	if err != nil {
		t.Fatalf("Observe() error = %v", err)
	}
	if result.State != ports.StorageResourceAvailable {
		t.Fatalf("State = %q, want available", result.State)
	}
	if result.ObservedAt != time.Unix(1700, 0).UTC() {
		t.Fatalf("ObservedAt = %v, want fixed clock", result.ObservedAt)
	}
	if client.observes != 1 {
		t.Fatalf("observes = %d, want 1", client.observes)
	}
}

func renderedStorageVolume(t *testing.T) []ports.WorkloadManifest {
	t.Helper()
	manifests, err := NewKubernetesStorageRenderer().RenderVolume(context.Background(), ports.StorageVolumeRecord{
		TenantID:     "tenant-a",
		VolumeID:     "vol-data",
		Name:         "data",
		SizeGiB:      100,
		StorageClass: "fast",
		State:        ports.StorageResourceAvailable,
	})
	if err != nil {
		t.Fatalf("RenderVolume() error = %v", err)
	}
	return manifests
}

func renderedStorageFilesystem(t *testing.T) []ports.WorkloadManifest {
	t.Helper()
	manifests, err := NewKubernetesStorageRenderer().RenderFilesystem(context.Background(), ports.StorageFilesystemRecord{
		TenantID:     "tenant-a",
		FilesystemID: "fs-shared",
		Name:         "shared",
		Protocol:     "nfs",
		SizeGiB:      500,
		State:        ports.StorageResourceAvailable,
	})
	if err != nil {
		t.Fatalf("RenderFilesystem() error = %v", err)
	}
	return manifests
}

type fakeKubernetesStorageProviderClient struct {
	dryRuns  int
	applies  int
	observes int
	status   ports.StorageProviderStatusResult
}

func (c *fakeKubernetesStorageProviderClient) ServerSideDryRun(_ context.Context, manifests []ports.WorkloadManifest) (ports.WorkloadProviderDryRunResult, error) {
	c.dryRuns++
	return ports.WorkloadProviderDryRunResult{
		Accepted:      true,
		Provider:      manifests[0].Provider,
		ManifestCount: len(manifests),
		Reason:        "accepted by Kubernetes server-side dry-run dryRun=All",
	}, nil
}

func (c *fakeKubernetesStorageProviderClient) ApplyManifests(_ context.Context, manifests []ports.WorkloadManifest) ([]string, error) {
	c.applies++
	return storageResourceRefs(manifests), nil
}

func (c *fakeKubernetesStorageProviderClient) ObserveStorageResource(_ context.Context, request ports.StorageProviderStatusRequest) (ports.StorageProviderStatusResult, error) {
	c.observes++
	if c.status.ResourceID != "" {
		return c.status, nil
	}
	return ports.StorageProviderStatusResult{
		TenantID:     request.TenantID,
		ResourceKind: request.ResourceKind,
		ResourceID:   request.ResourceID,
		Provider:     request.ApplyResult.Provider,
		ResourceRefs: append([]string(nil), request.ApplyResult.ResourceRefs...),
		State:        ports.StorageResourceAvailable,
	}, nil
}

var _ KubernetesStorageProviderClient = (*fakeKubernetesStorageProviderClient)(nil)
