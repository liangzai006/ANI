package router

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/kubercloud/ani/pkg/ports"
)

func TestDemoInstanceServiceCreatesVMContainerAndGPUContainer(t *testing.T) {
	api := newDemoInstanceAPI()
	for _, kind := range []string{"vm", "container", "gpu_container"} {
		spec, err := demoSpecFromRequest(demoCreateInstanceRequest{
			Kind:   kind,
			Name:   "demo-" + kind,
			CPU:    "2",
			Memory: "4Gi",
		}, "tenant-a")
		if err != nil {
			t.Fatalf("demoSpecFromRequest(%s) error = %v", kind, err)
		}
		result, err := api.service.Create(context.Background(), ports.WorkloadInstanceCreateRequest{
			Spec:            spec,
			UserID:          "user-a",
			PermissionProof: "demo:test",
			RequestedAt:     time.Now().UTC(),
		})
		if err != nil {
			t.Fatalf("Create(%s) error = %v", kind, err)
		}
		if result.FinalStatus.State != ports.WorkloadStateRunning {
			t.Fatalf("Create(%s) state = %s, want running", kind, result.FinalStatus.State)
		}
		if len(result.Manifests) != 1 {
			t.Fatalf("Create(%s) manifests = %d, want 1", kind, len(result.Manifests))
		}
	}
	records, err := api.service.List(context.Background(), ports.WorkloadInstanceListRequest{TenantID: "tenant-a"})
	if err != nil {
		t.Fatalf("List error = %v", err)
	}
	if len(records) != 3 {
		t.Fatalf("records = %d, want 3", len(records))
	}
}

func TestDemoInstanceServiceLifecycleAndOps(t *testing.T) {
	api := newDemoInstanceAPI()
	spec, err := demoSpecFromRequest(demoCreateInstanceRequest{Kind: "container", Name: "demo-app"}, "tenant-a")
	if err != nil {
		t.Fatalf("demoSpecFromRequest error = %v", err)
	}
	created, err := api.service.Create(context.Background(), ports.WorkloadInstanceCreateRequest{
		Spec:            spec,
		UserID:          "user-a",
		PermissionProof: "demo:test",
		RequestedAt:     time.Now().UTC(),
	})
	if err != nil {
		t.Fatalf("Create error = %v", err)
	}
	stopped, err := api.service.Stop(context.Background(), ports.WorkloadInstanceLifecycleRequest{
		TenantID:        "tenant-a",
		InstanceID:      created.Ref.InstanceID,
		UserID:          "user-a",
		PermissionProof: "demo:test",
		RequestedAt:     time.Now().UTC(),
	})
	if err != nil {
		t.Fatalf("Stop error = %v", err)
	}
	if stopped.Status.State != ports.WorkloadStateStopped {
		t.Fatalf("stopped state = %s, want stopped", stopped.Status.State)
	}
	started, err := api.service.Start(context.Background(), ports.WorkloadInstanceLifecycleRequest{
		TenantID:        "tenant-a",
		InstanceID:      created.Ref.InstanceID,
		UserID:          "user-a",
		PermissionProof: "demo:test",
		RequestedAt:     time.Now().UTC(),
	})
	if err != nil {
		t.Fatalf("Start error = %v", err)
	}
	if started.Status.State != ports.WorkloadStateRunning {
		t.Fatalf("started state = %s, want running", started.Status.State)
	}
	ops, err := api.service.Ops(context.Background(), ports.WorkloadInstanceOpsRequest{
		TenantID:        "tenant-a",
		InstanceID:      created.Ref.InstanceID,
		Action:          ports.WorkloadInstanceOpsLogs,
		UserID:          "user-a",
		PermissionProof: "demo:test",
		RequestedAt:     time.Now().UTC(),
	})
	if err != nil {
		t.Fatalf("Ops error = %v", err)
	}
	if !ops.Accepted {
		t.Fatalf("ops accepted = false, want true")
	}
}

func TestDemoInstanceOperationsAreQueryable(t *testing.T) {
	api := newDemoInstanceAPI()
	spec, err := demoSpecFromRequest(demoCreateInstanceRequest{Kind: "container", Name: "demo-ops"}, "tenant-a")
	if err != nil {
		t.Fatalf("demoSpecFromRequest error = %v", err)
	}
	created, err := api.service.Create(context.Background(), ports.WorkloadInstanceCreateRequest{
		IdempotencyKey:  "demo-create-ops",
		Spec:            spec,
		UserID:          "user-a",
		PermissionProof: "demo:test",
		RequestedAt:     time.Now().UTC(),
	})
	if err != nil {
		t.Fatalf("Create error = %v", err)
	}
	if created.OperationID == "" {
		t.Fatalf("OperationID is empty")
	}
	list, err := api.operations.ListOperations(context.Background(), ports.WorkloadOperationListRequest{
		TenantID:   "tenant-a",
		InstanceID: created.Ref.InstanceID,
	})
	if err != nil {
		t.Fatalf("ListOperations error = %v", err)
	}
	if len(list.Items) != 1 {
		t.Fatalf("operations = %d, want 1", len(list.Items))
	}
	if len(list.Items[0].Steps) == 0 {
		t.Fatalf("operation steps are empty")
	}
	got, err := api.operations.GetOperation(context.Background(), "tenant-a", created.OperationID)
	if err != nil {
		t.Fatalf("GetOperation error = %v", err)
	}
	if got.ID != created.OperationID || got.Status != ports.WorkloadOperationSucceeded {
		t.Fatalf("operation id=%q status=%s, want %q/succeeded", got.ID, got.Status, created.OperationID)
	}
}

func TestDemoInstanceServiceVMConsoleSession(t *testing.T) {
	api := newDemoInstanceAPI()
	spec, err := demoSpecFromRequest(demoCreateInstanceRequest{Kind: "vm", Name: "demo-vm"}, "tenant-a")
	if err != nil {
		t.Fatalf("demoSpecFromRequest error = %v", err)
	}
	created, err := api.service.Create(context.Background(), ports.WorkloadInstanceCreateRequest{
		Spec:            spec,
		UserID:          "user-a",
		PermissionProof: "demo:test",
		RequestedAt:     time.Now().UTC(),
	})
	if err != nil {
		t.Fatalf("Create error = %v", err)
	}
	console, err := api.service.Ops(context.Background(), ports.WorkloadInstanceOpsRequest{
		TenantID:        "tenant-a",
		InstanceID:      created.Ref.InstanceID,
		Action:          ports.WorkloadInstanceOpsVMVNC,
		Protocol:        "vnc",
		UserID:          "user-a",
		PermissionProof: "demo:test",
		RequestedAt:     time.Now().UTC(),
	})
	if err != nil {
		t.Fatalf("Ops(vm_vnc) error = %v", err)
	}
	if !console.Accepted || console.Protocol != "vnc" || console.ConnectURL == "" {
		t.Fatalf("console accepted=%v protocol=%q connect=%q, want vnc connect session", console.Accepted, console.Protocol, console.ConnectURL)
	}
}

func TestDemoInstanceServiceRealShellExecutesCommand(t *testing.T) {
	record := ports.WorkloadInstanceRecord{
		TenantID:   "tenant-a",
		InstanceID: "instance-shell",
		Name:       "demo-vm-shell",
		Kind:       ports.WorkloadKindVM,
		Provider:   "kubevirt",
		Status:     ports.WorkloadStatus{State: ports.WorkloadStateRunning},
	}
	result, err := runDemoShellCommand(context.Background(), record, "printf hello")
	if err != nil {
		t.Fatalf("runDemoShellCommand error = %v", err)
	}
	if result.ExitCode != 0 || strings.TrimSpace(result.Output) != "hello" {
		t.Fatalf("result exit=%d output=%q, want hello", result.ExitCode, result.Output)
	}
	if result.CWD == "" {
		t.Fatalf("CWD is empty")
	}
}
