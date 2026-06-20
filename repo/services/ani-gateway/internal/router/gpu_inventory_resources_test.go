package router

import (
	"context"
	"testing"

	"github.com/kubercloud/ani/pkg/ports"
)

func TestGPUInventoryAPIListsInventoryAndOccupancy(t *testing.T) {
	api := newGPUInventoryAPI()
	records, err := api.inventory.ListNodeClasses(context.Background(), api.gpuFilter("", "", ""))
	if err != nil {
		t.Fatalf("ListNodeClasses error = %v", err)
	}
	listResponse := api.gpuInventoryListFromNodes(records, "", "", "")
	if len(listResponse.Items) == 0 || listResponse.Total != len(listResponse.Items) {
		t.Fatalf("inventory response = %+v, want items and total", listResponse)
	}
	requireLocalCoreDevProfile(t, listResponse.DevProfile, "local-gpu-inventory")
	if listResponse.Items[0].ID == "" || listResponse.Items[0].NodeName == "" || listResponse.Items[0].GPUType == "" {
		t.Fatalf("first GPU = %+v, want schema fields", listResponse.Items[0])
	}
	requireLocalCoreDevProfile(t, listResponse.Items[0].DevProfile, "local-gpu-inventory")

	occupancy := api.gpuOccupancyFromNodes(records)
	if occupancy.Total != len(listResponse.Items) || occupancy.Available+occupancy.InUse+occupancy.Fault != occupancy.Total {
		t.Fatalf("occupancy = %+v, inventory total = %d", occupancy, len(listResponse.Items))
	}
	if len(occupancy.ByGPUType) == 0 {
		t.Fatalf("occupancy by_gpu_type is empty")
	}
	requireLocalCoreDevProfile(t, occupancy.DevProfile, "local-gpu-inventory")
}

func TestGPUInventoryAPISandboxTemplatesUseLocalCatalog(t *testing.T) {
	api := newGPUInventoryAPI()
	result, err := api.templates.ListSandboxTemplates(context.Background(), api.sandboxTemplateListRequest(10, ""))
	if err != nil {
		t.Fatalf("ListSandboxTemplates error = %v", err)
	}
	response := api.sandboxTemplateListFromResult(result)
	if len(response.Items) == 0 || response.Total != len(response.Items) {
		t.Fatalf("templates response = %+v, want items and total", response)
	}
	if response.Items[0].ID == "" || response.Items[0].Image == "" || !response.Items[0].IsBuiltin {
		t.Fatalf("template = %+v, want builtin schema fields", response.Items[0])
	}
	requireLocalCoreDevProfile(t, response.DevProfile, "local-sandbox-template-catalog")
	requireLocalCoreDevProfile(t, response.Items[0].DevProfile, "local-sandbox-template-catalog")
}

func TestGPUInventoryAPIWithProviderMarksRealDevProfile(t *testing.T) {
	api := newGPUInventoryAPIWithInventory(fakeGPUInventory{nodes: []ports.GPUNodeClass{{
		NodeName: "gpu-node-a",
		Vendor:   ports.GPUVendorNVIDIA,
		Model:    "NVIDIA-L40S",
		Ready:    true,
		Devices: []ports.GPUDeviceClass{{
			Vendor:        ports.GPUVendorNVIDIA,
			Model:         "NVIDIA-L40S",
			ResourceName:  "nvidia.com/gpu",
			DriverVersion: "device-plugin",
		}},
	}}})

	records, err := api.inventory.ListNodeClasses(context.Background(), api.gpuFilter("", "", ""))
	if err != nil {
		t.Fatalf("ListNodeClasses error = %v", err)
	}
	listResponse := api.gpuInventoryListFromNodes(records, "", "", "")
	if listResponse.DevProfile.Mode != "real" || !listResponse.DevProfile.RealProvider || listResponse.DevProfile.Provider != "kubernetes-gpu-inventory" {
		t.Fatalf("list dev_profile = %+v, want Kubernetes GPU real provider", listResponse.DevProfile)
	}
	if len(listResponse.Items) != 1 || listResponse.Items[0].DevProfile.Provider != "kubernetes-gpu-inventory" || !listResponse.Items[0].DevProfile.RealProvider {
		t.Fatalf("items = %+v, want real provider item profile", listResponse.Items)
	}

	occupancy := api.gpuOccupancyFromNodes(records)
	if occupancy.DevProfile.Mode != "real" || !occupancy.DevProfile.RealProvider || occupancy.DevProfile.Provider != "kubernetes-gpu-inventory" {
		t.Fatalf("occupancy dev_profile = %+v, want Kubernetes GPU real provider", occupancy.DevProfile)
	}
}

type fakeGPUInventory struct {
	nodes []ports.GPUNodeClass
}

func (f fakeGPUInventory) ListNodeClasses(context.Context, ports.GPUDiscoveryFilter) ([]ports.GPUNodeClass, error) {
	return f.nodes, nil
}

func (f fakeGPUInventory) GetNodeClass(context.Context, string) (ports.GPUNodeClass, error) {
	if len(f.nodes) == 0 {
		return ports.GPUNodeClass{}, ports.ErrNotFound
	}
	return f.nodes[0], nil
}

func (f fakeGPUInventory) PlanScheduling(context.Context, ports.GPUSchedulingRequest) (ports.GPUSchedulingDecision, error) {
	return ports.GPUSchedulingDecision{}, ports.ErrUnsupported
}
