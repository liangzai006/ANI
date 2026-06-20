package bootstrap

import (
	"strings"
	"testing"
	"time"

	"github.com/kubercloud/ani/pkg/adapters/objectstore"
	runtimeadapter "github.com/kubercloud/ani/pkg/adapters/runtime"
	"github.com/kubercloud/ani/pkg/adapters/vectorstore"
	"github.com/kubercloud/ani/pkg/ports"
)

func TestConnectMetadataStoreRejectsInvalidDatabaseURL(t *testing.T) {
	store, closeStore, err := ConnectMetadataStore(t.Context(), ":// invalid")
	if err == nil {
		t.Fatalf("ConnectMetadataStore() error = nil, want invalid database URL error")
	}
	if store != nil {
		t.Fatalf("store = %T, want nil", store)
	}
	if closeStore == nil {
		t.Fatalf("closeStore = nil, want no-op close function")
	}
	closeStore()
}

func TestNewCapabilitiesDefaultsToLocalProviderAdapters(t *testing.T) {
	capabilities, err := NewCapabilitiesWithConfig(nil, nil, nil, Config{})
	if err != nil {
		t.Fatalf("NewCapabilitiesWithConfig() error = %v", err)
	}
	if _, ok := capabilities.WorkloadDryRun.(*runtimeadapter.LocalProviderDryRun); !ok {
		t.Fatalf("WorkloadDryRun = %T, want LocalProviderDryRun", capabilities.WorkloadDryRun)
	}
	if _, ok := capabilities.WorkloadApply.(*runtimeadapter.LocalProviderApply); !ok {
		t.Fatalf("WorkloadApply = %T, want LocalProviderApply", capabilities.WorkloadApply)
	}
	if _, ok := capabilities.WorkloadStatus.(*runtimeadapter.LocalProviderStatusReader); !ok {
		t.Fatalf("WorkloadStatus = %T, want LocalProviderStatusReader", capabilities.WorkloadStatus)
	}
	if _, ok := capabilities.WorkloadOperations.(*runtimeadapter.MetadataOperationStore); !ok {
		t.Fatalf("WorkloadOperations = %T, want MetadataOperationStore", capabilities.WorkloadOperations)
	}
	if _, ok := capabilities.WorkloadIdentity.(*runtimeadapter.MetadataWorkloadIdentityService); !ok {
		t.Fatalf("WorkloadIdentity = %T, want MetadataWorkloadIdentityService", capabilities.WorkloadIdentity)
	}
	if _, ok := capabilities.WorkloadController.(*runtimeadapter.LocalWorkloadReconcileController); !ok {
		t.Fatalf("WorkloadController = %T, want LocalWorkloadReconcileController", capabilities.WorkloadController)
	}
	if _, ok := capabilities.InstanceService.(*runtimeadapter.LocalInstanceService); !ok {
		t.Fatalf("InstanceService = %T, want LocalInstanceService with operation store", capabilities.InstanceService)
	}
	if _, ok := capabilities.InstanceObservability.(*runtimeadapter.LocalInstanceObservabilityService); !ok {
		t.Fatalf("InstanceObservability = %T, want LocalInstanceObservabilityService", capabilities.InstanceObservability)
	}
	if _, ok := capabilities.NetworkStore.(*runtimeadapter.MetadataNetworkStore); !ok {
		t.Fatalf("NetworkStore = %T, want MetadataNetworkStore", capabilities.NetworkStore)
	}
	if _, ok := capabilities.NetworkRenderer.(*runtimeadapter.KubeOVNNetworkRenderer); !ok {
		t.Fatalf("NetworkRenderer = %T, want KubeOVNNetworkRenderer", capabilities.NetworkRenderer)
	}
	if _, ok := capabilities.NetworkDryRun.(*runtimeadapter.KubeOVNNetworkProviderAdapter); !ok {
		t.Fatalf("NetworkDryRun = %T, want KubeOVNNetworkProviderAdapter", capabilities.NetworkDryRun)
	}
	if _, ok := capabilities.NetworkApply.(*runtimeadapter.KubeOVNNetworkProviderAdapter); !ok {
		t.Fatalf("NetworkApply = %T, want KubeOVNNetworkProviderAdapter", capabilities.NetworkApply)
	}
	if _, ok := capabilities.NetworkStatus.(*runtimeadapter.KubeOVNNetworkProviderAdapter); !ok {
		t.Fatalf("NetworkStatus = %T, want KubeOVNNetworkProviderAdapter", capabilities.NetworkStatus)
	}
	if _, ok := capabilities.NetworkReconcile.(*runtimeadapter.LocalNetworkStatusReconciler); !ok {
		t.Fatalf("NetworkReconcile = %T, want LocalNetworkStatusReconciler", capabilities.NetworkReconcile)
	}
	if _, ok := capabilities.NetworkResources.(*runtimeadapter.LocalNetworkService); !ok {
		t.Fatalf("NetworkResources = %T, want LocalNetworkService with network store", capabilities.NetworkResources)
	}
	if _, ok := capabilities.StorageResources.(*runtimeadapter.LocalStorageService); !ok {
		t.Fatalf("StorageResources = %T, want LocalStorageService", capabilities.StorageResources)
	}
	if _, ok := capabilities.StorageStore.(*runtimeadapter.MetadataStorageStore); !ok {
		t.Fatalf("StorageStore = %T, want MetadataStorageStore", capabilities.StorageStore)
	}
	if _, ok := capabilities.StorageRenderer.(*runtimeadapter.KubernetesStorageRenderer); !ok {
		t.Fatalf("StorageRenderer = %T, want KubernetesStorageRenderer", capabilities.StorageRenderer)
	}
	if _, ok := capabilities.StorageDryRun.(*runtimeadapter.KubernetesStorageProviderAdapter); !ok {
		t.Fatalf("StorageDryRun = %T, want KubernetesStorageProviderAdapter", capabilities.StorageDryRun)
	}
	if _, ok := capabilities.StorageApply.(*runtimeadapter.KubernetesStorageProviderAdapter); !ok {
		t.Fatalf("StorageApply = %T, want KubernetesStorageProviderAdapter", capabilities.StorageApply)
	}
	if _, ok := capabilities.StorageStatus.(*runtimeadapter.KubernetesStorageProviderAdapter); !ok {
		t.Fatalf("StorageStatus = %T, want KubernetesStorageProviderAdapter", capabilities.StorageStatus)
	}
	if _, ok := capabilities.StorageReconcile.(*runtimeadapter.LocalStorageStatusReconciler); !ok {
		t.Fatalf("StorageReconcile = %T, want LocalStorageStatusReconciler", capabilities.StorageReconcile)
	}
	if _, ok := capabilities.VectorStoreResources.(*runtimeadapter.LocalVectorStoreService); !ok {
		t.Fatalf("VectorStoreResources = %T, want LocalVectorStoreService", capabilities.VectorStoreResources)
	}
}

func TestNewCapabilitiesCanWireKubernetesRESTProvider(t *testing.T) {
	capabilities, err := NewCapabilitiesWithConfig(nil, nil, nil, Config{
		WorkloadProvider:               "kubernetes_rest",
		KubernetesAPIHost:              "https://kubernetes.example.test",
		KubernetesProviderFieldManager: "ani-test",
	})
	if err != nil {
		t.Fatalf("NewCapabilitiesWithConfig() error = %v", err)
	}
	if _, ok := capabilities.WorkloadDryRun.(*runtimeadapter.KubernetesProviderAdapter); !ok {
		t.Fatalf("WorkloadDryRun = %T, want KubernetesProviderAdapter", capabilities.WorkloadDryRun)
	}
	if _, ok := capabilities.WorkloadApply.(*runtimeadapter.KubernetesProviderAdapter); !ok {
		t.Fatalf("WorkloadApply = %T, want KubernetesProviderAdapter", capabilities.WorkloadApply)
	}
	if _, ok := capabilities.WorkloadStatus.(*runtimeadapter.KubernetesProviderAdapter); !ok {
		t.Fatalf("WorkloadStatus = %T, want KubernetesProviderAdapter", capabilities.WorkloadStatus)
	}
}

func TestNewCapabilitiesCanWireKubeOVNNetworkRouteProvider(t *testing.T) {
	capabilities, err := NewCapabilitiesWithConfig(nil, nil, nil, Config{
		NetworkProvider:                "kubeovn_rest",
		NetworkProviderApplyEnabled:    true,
		NetworkProviderUserID:          "ani-core-network-provider",
		NetworkProviderPermissionProof: "rbac-scope:networks.routes.write",
		KubernetesAPIHost:              "https://kubernetes.example.test",
		KubernetesProviderFieldManager: "ani-test",
	})
	if err != nil {
		t.Fatalf("NewCapabilitiesWithConfig() error = %v", err)
	}
	if _, ok := capabilities.NetworkResources.(*runtimeadapter.LocalNetworkService); !ok {
		t.Fatalf("NetworkResources = %T, want LocalNetworkService with Kube-OVN route provider", capabilities.NetworkResources)
	}
	if _, ok := capabilities.NetworkDryRun.(*runtimeadapter.KubeOVNNetworkProviderAdapter); !ok {
		t.Fatalf("NetworkDryRun = %T, want KubeOVNNetworkProviderAdapter", capabilities.NetworkDryRun)
	}
}

func TestNewCapabilitiesRejectsKubeOVNNetworkProviderWithoutExecutionProof(t *testing.T) {
	if _, err := NewCapabilitiesWithConfig(nil, nil, nil, Config{
		NetworkProvider:   "kubeovn_rest",
		KubernetesAPIHost: "https://kubernetes.example.test",
	}); err == nil {
		t.Fatalf("NewCapabilitiesWithConfig() error = nil, want missing network provider proof error")
	}
}

func TestNewCapabilitiesCanWireKubernetesStorageProvider(t *testing.T) {
	capabilities, err := NewCapabilitiesWithConfig(nil, nil, nil, Config{
		StorageProvider:                "kubernetes_rest",
		StorageProviderApplyEnabled:    true,
		StorageProviderUserID:          "ani-core-storage-provider",
		StorageProviderPermissionProof: "rbac-scope:storage.write",
		KubernetesAPIHost:              "https://kubernetes.example.test",
		KubernetesProviderFieldManager: "ani-test",
	})
	if err != nil {
		t.Fatalf("NewCapabilitiesWithConfig() error = %v", err)
	}
	if _, ok := capabilities.StorageResources.(*runtimeadapter.LocalStorageService); !ok {
		t.Fatalf("StorageResources = %T, want LocalStorageService with Kubernetes storage provider", capabilities.StorageResources)
	}
	if _, ok := capabilities.StorageDryRun.(*runtimeadapter.KubernetesStorageProviderAdapter); !ok {
		t.Fatalf("StorageDryRun = %T, want KubernetesStorageProviderAdapter", capabilities.StorageDryRun)
	}
}

func TestNewCapabilitiesRejectsKubernetesStorageProviderWithoutExecutionProof(t *testing.T) {
	if _, err := NewCapabilitiesWithConfig(nil, nil, nil, Config{
		StorageProvider:   "kubernetes_rest",
		KubernetesAPIHost: "https://kubernetes.example.test",
	}); err == nil {
		t.Fatalf("NewCapabilitiesWithConfig() error = nil, want missing storage provider proof error")
	}
}

func TestNewCapabilitiesCanWireMinIOObjectStoreProvider(t *testing.T) {
	capabilities, err := NewCapabilitiesWithConfig(nil, nil, nil, Config{
		ObjectStoreProvider:        "minio",
		ObjectStoreEndpoint:        "https://minio.example:9000",
		ObjectStoreAccessKeyID:     "minio",
		ObjectStoreSecretAccessKey: "secret",
		ObjectStoreRegion:          "us-east-1",
	})
	if err != nil {
		t.Fatalf("NewCapabilitiesWithConfig() error = %v", err)
	}
	if _, ok := capabilities.ObjectStore.(*objectstore.MinIOObjectStore); !ok {
		t.Fatalf("ObjectStore = %T, want MinIOObjectStore", capabilities.ObjectStore)
	}
	signed, err := capabilities.ObjectStore.SignedUploadURL(t.Context(), ports.ObjectRef{
		TenantID:    "tenant-a",
		BucketClass: ports.BucketClass("models-a"),
		ObjectKey:   "model.bin",
	}, 10*time.Minute)
	if err != nil {
		t.Fatalf("SignedUploadURL() error = %v", err)
	}
	if !strings.HasPrefix(signed.URL, "https://minio.example:9000/models-a/tenant-a/model.bin?") {
		t.Fatalf("signed URL = %q, want MinIO endpoint prefix", signed.URL)
	}
}

func TestNewCapabilitiesCanWireMilvusVectorStoreProvider(t *testing.T) {
	capabilities, err := NewCapabilitiesWithConfig(nil, nil, nil, Config{
		VectorStoreProvider: "milvus",
		VectorStoreEndpoint: "http://milvus.example:19530",
		VectorStoreToken:    "milvus-token",
		VectorStoreDatabase: "ani",
	})
	if err != nil {
		t.Fatalf("NewCapabilitiesWithConfig() error = %v", err)
	}
	if _, ok := capabilities.VectorStore.(*vectorstore.MilvusVectorStore); !ok {
		t.Fatalf("VectorStore = %T, want MilvusVectorStore", capabilities.VectorStore)
	}
	if _, ok := capabilities.VectorStoreResources.(*runtimeadapter.LocalVectorStoreService); !ok {
		t.Fatalf("VectorStoreResources = %T, want LocalVectorStoreService with backend", capabilities.VectorStoreResources)
	}
}

func TestNewCapabilitiesCanWireKubernetesRESTLifecycleProvider(t *testing.T) {
	capabilities, err := NewCapabilitiesWithConfig(nil, nil, nil, Config{
		WorkloadLifecycleProvider: "kubernetes_rest",
		KubernetesAPIHost:         "https://kubernetes.example.test",
	})
	if err != nil {
		t.Fatalf("NewCapabilitiesWithConfig() error = %v", err)
	}
	if _, ok := capabilities.InstanceService.(*runtimeadapter.LocalInstanceService); !ok {
		t.Fatalf("InstanceService = %T, want LocalInstanceService with lifecycle executor", capabilities.InstanceService)
	}
}

func TestNewCapabilitiesCanWireKubernetesRESTOpsProvider(t *testing.T) {
	capabilities, err := NewCapabilitiesWithConfig(nil, nil, nil, Config{
		WorkloadOpsProvider: "kubernetes_rest",
		KubernetesAPIHost:   "https://kubernetes.example.test",
	})
	if err != nil {
		t.Fatalf("NewCapabilitiesWithConfig() error = %v", err)
	}
	if _, ok := capabilities.InstanceOps.(*runtimeadapter.KubernetesInstanceOps); !ok {
		t.Fatalf("InstanceOps = %T, want KubernetesInstanceOps", capabilities.InstanceOps)
	}
}

func TestNewCapabilitiesCanWirePrometheusInstanceObservabilityProvider(t *testing.T) {
	capabilities, err := NewCapabilitiesWithConfig(nil, nil, nil, Config{
		InstanceObservabilityProvider:      "prometheus_kubernetes",
		InstanceObservabilityPrometheusURL: "https://prometheus.example.test",
		KubernetesAPIHost:                  "https://kubernetes.example.test",
		InstanceObservabilityExecBaseURL:   "wss://gateway.example.test/api/v1",
	})
	if err != nil {
		t.Fatalf("NewCapabilitiesWithConfig() error = %v", err)
	}
	if _, ok := capabilities.InstanceObservability.(*runtimeadapter.PrometheusInstanceObservability); !ok {
		t.Fatalf("InstanceObservability = %T, want PrometheusInstanceObservability", capabilities.InstanceObservability)
	}
}

func TestNewCapabilitiesCanWrapReconcileControllerWithMetadataLeaderElection(t *testing.T) {
	capabilities, err := NewCapabilitiesWithConfig(nil, nil, nil, Config{
		WorkloadReconcileLeaderElectionEnabled: true,
		WorkloadReconcileLeaderIdentity:        "worker-a",
	})
	if err != nil {
		t.Fatalf("NewCapabilitiesWithConfig() error = %v", err)
	}
	if _, ok := capabilities.WorkloadController.(*runtimeadapter.LeaderElectingWorkloadReconcileController); !ok {
		t.Fatalf("WorkloadController = %T, want LeaderElectingWorkloadReconcileController", capabilities.WorkloadController)
	}
}

func TestNewCapabilitiesRejectsLeaderElectionWithoutIdentity(t *testing.T) {
	if _, err := NewCapabilitiesWithConfig(nil, nil, nil, Config{
		WorkloadReconcileLeaderElectionEnabled: true,
	}); err == nil {
		t.Fatalf("NewCapabilitiesWithConfig() error = nil, want missing leader identity error")
	}
}

func TestNewCapabilitiesRejectsKubernetesRESTWithoutHost(t *testing.T) {
	if _, err := NewCapabilitiesWithConfig(nil, nil, nil, Config{WorkloadProvider: "kubernetes_rest"}); err == nil {
		t.Fatalf("NewCapabilitiesWithConfig() error = nil, want missing Kubernetes host error")
	}
}

func TestNewCapabilitiesRejectsKubernetesRESTOpsWithoutHost(t *testing.T) {
	if _, err := NewCapabilitiesWithConfig(nil, nil, nil, Config{WorkloadOpsProvider: "kubernetes_rest"}); err == nil {
		t.Fatalf("NewCapabilitiesWithConfig() error = nil, want missing Kubernetes host error")
	}
}

func TestNewCapabilitiesRejectsKubernetesRESTLifecycleWithoutHost(t *testing.T) {
	if _, err := NewCapabilitiesWithConfig(nil, nil, nil, Config{WorkloadLifecycleProvider: "kubernetes_rest"}); err == nil {
		t.Fatalf("NewCapabilitiesWithConfig() error = nil, want missing Kubernetes host error")
	}
}
