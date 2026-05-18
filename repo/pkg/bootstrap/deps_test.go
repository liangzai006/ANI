package bootstrap

import (
	"testing"

	runtimeadapter "github.com/kubercloud/ani/pkg/adapters/runtime"
)

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
	if _, ok := capabilities.InstanceService.(*runtimeadapter.LocalInstanceService); !ok {
		t.Fatalf("InstanceService = %T, want LocalInstanceService with operation store", capabilities.InstanceService)
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
