package runtime

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"

	"github.com/kubercloud/ani/pkg/ports"
)

func TestKubernetesNodePoolProviderAdapterRendersClusterAPIMachineDeployment(t *testing.T) {
	client := &fakeNodePoolProviderClient{}
	adapter := NewKubernetesNodePoolProviderAdapter(client)

	result, err := adapter.ApplyK8sClusterNodePool(context.Background(), ports.K8sClusterNodePoolProviderRequest{
		Operation:    "create",
		TenantID:     "tenant-a",
		ClusterID:    "k8sclu-provider",
		ClusterName:  "vc-a",
		NodePoolID:   "k8snp-gpu",
		Name:         "gpu-pool",
		NodeCount:    2,
		InstanceType: "gpu.l4.xlarge",
		GPU: ports.K8sClusterNodePoolGPU{
			Vendor:       "nvidia",
			Model:        "L4",
			Count:        1,
			ResourceName: "nvidia.com/gpu",
		},
	})
	if err != nil {
		t.Fatalf("ApplyK8sClusterNodePool() error = %v", err)
	}
	if !result.Applied || result.Provider != "clusterapi" {
		t.Fatalf("result = %+v, want applied clusterapi", result)
	}
	if len(client.manifests) != 1 {
		t.Fatalf("manifest count = %d, want 1", len(client.manifests))
	}
	manifest := client.manifests[0]
	if manifest.Provider != "clusterapi" || manifest.Kind != "MachineDeployment" || manifest.Name != "gpu-pool" {
		t.Fatalf("manifest metadata = %+v, want Cluster API MachineDeployment gpu-pool", manifest)
	}
	var doc map[string]any
	if err := json.Unmarshal([]byte(manifest.Content), &doc); err != nil {
		t.Fatalf("manifest content is not JSON: %v", err)
	}
	metadata := doc["metadata"].(map[string]any)
	if metadata["namespace"] != "ani-tenant-tenant-a" {
		t.Fatalf("namespace = %v, want tenant namespace", metadata["namespace"])
	}
	spec := doc["spec"].(map[string]any)
	if spec["clusterName"] != "vc-a" || spec["replicas"].(float64) != 2 {
		t.Fatalf("spec = %+v, want clusterName vc-a replicas 2", spec)
	}
	template := spec["template"].(map[string]any)
	templateMetadata := template["metadata"].(map[string]any)
	templateAnnotations := templateMetadata["annotations"].(map[string]any)
	machineSpec := template["spec"].(map[string]any)
	if machineSpec["clusterName"] != "vc-a" {
		t.Fatalf("machine spec = %+v, want clusterName vc-a", machineSpec)
	}
	if machineSpec["bootstrap"] == nil || machineSpec["infrastructureRef"] == nil {
		t.Fatalf("machine spec = %+v, want CAPI bootstrap and infrastructureRef", machineSpec)
	}
	if templateAnnotations["ani.kubercloud.io/instance-type"] != "gpu.l4.xlarge" {
		t.Fatalf("template annotations = %+v, want instance type", templateAnnotations)
	}
	if templateAnnotations["ani.kubercloud.io/gpu-count"] != "1" || templateAnnotations["ani.kubercloud.io/gpu-resource-name"] != "nvidia.com/gpu" {
		t.Fatalf("template annotations = %+v, want GPU intent", templateAnnotations)
	}
	if !strings.Contains(manifest.Content, `"nvidia.com/gpu"`) || !strings.Contains(manifest.Content, `"ani.kubercloud.io/gpu-vendor"`) {
		t.Fatalf("manifest content = %s, want GPU scheduling labels", manifest.Content)
	}
}

func TestKubernetesNodePoolProviderAdapterRendersDeleteIntentAsZeroReplicas(t *testing.T) {
	client := &fakeNodePoolProviderClient{}
	adapter := NewKubernetesNodePoolProviderAdapter(client)

	result, err := adapter.DeleteK8sClusterNodePool(context.Background(), ports.K8sClusterNodePoolProviderRequest{
		TenantID:     "tenant-a",
		ClusterID:    "k8sclu-provider",
		ClusterName:  "vc-a",
		NodePoolID:   "k8snp-gpu",
		Name:         "gpu-pool",
		NodeCount:    2,
		InstanceType: "gpu.l4.xlarge",
	})
	if err != nil {
		t.Fatalf("DeleteK8sClusterNodePool() error = %v", err)
	}
	if !result.Applied || result.Reason != "Cluster API MachineDeployment delete intent applied" {
		t.Fatalf("result = %+v, want delete intent applied", result)
	}
	var doc map[string]any
	if err := json.Unmarshal([]byte(client.manifests[0].Content), &doc); err != nil {
		t.Fatalf("manifest content is not JSON: %v", err)
	}
	spec := doc["spec"].(map[string]any)
	if spec["replicas"].(float64) != 0 {
		t.Fatalf("replicas = %v, want zero replica delete intent", spec["replicas"])
	}
	metadata := doc["metadata"].(map[string]any)
	annotations := metadata["annotations"].(map[string]any)
	if annotations["ani.kubercloud.io/delete-intent"] != "true" {
		t.Fatalf("annotations = %+v, want delete intent annotation", annotations)
	}
}

func TestKubernetesNodePoolProviderAdapterRendersConfiguredCAPKRefs(t *testing.T) {
	client := &fakeNodePoolProviderClient{}
	adapter := NewKubernetesNodePoolProviderAdapter(
		client,
		WithKubernetesNodePoolProviderConfig(KubernetesNodePoolProviderConfig{
			MachineVersion:                "v1.36.1",
			BootstrapRefAPIVersion:        "bootstrap.cluster.x-k8s.io/v1beta1",
			BootstrapRefKind:              "KubeadmConfigTemplate",
			BootstrapRefNameTemplate:      "{cluster_name}-{node_pool_name}",
			BootstrapRefNamespace:         "{namespace}",
			InfrastructureRefAPIVersion:   "infrastructure.cluster.x-k8s.io/v1alpha1",
			InfrastructureRefKind:         "KubevirtMachineTemplate",
			InfrastructureRefNameTemplate: "{cluster_name}-{node_pool_name}",
			InfrastructureRefNamespace:    "{namespace}",
		}),
	)

	_, err := adapter.ApplyK8sClusterNodePool(context.Background(), ports.K8sClusterNodePoolProviderRequest{
		Operation:    "create",
		TenantID:     "tenant-a",
		ClusterID:    "k8sclu-provider",
		ClusterName:  "vc-a",
		NodePoolID:   "k8snp-gpu",
		Name:         "gpu-pool",
		NodeCount:    2,
		InstanceType: "gpu.l4.xlarge",
	})
	if err != nil {
		t.Fatalf("ApplyK8sClusterNodePool() error = %v", err)
	}
	var doc map[string]any
	if err := json.Unmarshal([]byte(client.manifests[0].Content), &doc); err != nil {
		t.Fatalf("manifest content is not JSON: %v", err)
	}
	spec := doc["spec"].(map[string]any)
	template := spec["template"].(map[string]any)
	machineSpec := template["spec"].(map[string]any)
	if machineSpec["version"] != "v1.36.1" {
		t.Fatalf("machine version = %v, want v1.36.1", machineSpec["version"])
	}
	bootstrap := machineSpec["bootstrap"].(map[string]any)
	configRef := bootstrap["configRef"].(map[string]any)
	if configRef["apiVersion"] != "bootstrap.cluster.x-k8s.io/v1beta1" || configRef["kind"] != "KubeadmConfigTemplate" || configRef["name"] != "vc-a-gpu-pool" || configRef["namespace"] != "ani-tenant-tenant-a" {
		t.Fatalf("bootstrap configRef = %+v, want CAPK KubeadmConfigTemplate ref", configRef)
	}
	infraRef := machineSpec["infrastructureRef"].(map[string]any)
	if infraRef["apiVersion"] != "infrastructure.cluster.x-k8s.io/v1alpha1" || infraRef["kind"] != "KubevirtMachineTemplate" || infraRef["name"] != "vc-a-gpu-pool" || infraRef["namespace"] != "ani-tenant-tenant-a" {
		t.Fatalf("infrastructureRef = %+v, want CAPK KubevirtMachineTemplate ref", infraRef)
	}
}

func TestKubernetesNodePoolProviderAdapterRejectsPartialBootstrapConfigRef(t *testing.T) {
	client := &fakeNodePoolProviderClient{}
	adapter := NewKubernetesNodePoolProviderAdapter(
		client,
		WithKubernetesNodePoolProviderConfig(KubernetesNodePoolProviderConfig{
			BootstrapRefKind: "KubeadmConfigTemplate",
		}),
	)

	_, err := adapter.ApplyK8sClusterNodePool(context.Background(), ports.K8sClusterNodePoolProviderRequest{
		Operation:    "create",
		TenantID:     "tenant-a",
		ClusterID:    "k8sclu-provider",
		ClusterName:  "vc-a",
		NodePoolID:   "k8snp-gpu",
		Name:         "gpu-pool",
		NodeCount:    2,
		InstanceType: "gpu.l4.xlarge",
	})
	if !errors.Is(err, ports.ErrInvalid) {
		t.Fatalf("ApplyK8sClusterNodePool() error = %v, want ErrInvalid", err)
	}
}

type fakeNodePoolProviderClient struct {
	manifests []ports.WorkloadManifest
}

func (c *fakeNodePoolProviderClient) ApplyManifests(_ context.Context, manifests []ports.WorkloadManifest) ([]string, error) {
	c.manifests = append([]ports.WorkloadManifest(nil), manifests...)
	return []string{"clusterapi/MachineDeployment/" + manifests[0].Name}, nil
}
