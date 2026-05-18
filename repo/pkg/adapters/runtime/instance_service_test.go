package runtime

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/kubercloud/ani/pkg/ports"
)

func TestLocalInstanceServiceCreatesContainerThroughOrchestrator(t *testing.T) {
	orchestrator := &fakeInstanceOrchestrator{}
	service := NewLocalInstanceService(orchestrator, &fakeInstanceStore{}, NewLocalInstanceOpsGuard())
	result, err := service.Create(context.Background(), ports.WorkloadInstanceCreateRequest{
		Spec: ports.WorkloadSpec{
			TenantID: "tenant-a",
			Name:     "app-01",
			Kind:     ports.WorkloadKindContainer,
			Image:    "harbor/app:1",
		},
		UserID:          "user-a",
		PermissionProof: "rbac:create:workload",
	})
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}
	if orchestrator.creates != 1 {
		t.Fatalf("creates = %d, want 1", orchestrator.creates)
	}
	if result.Ref.InstanceID == "" {
		t.Fatalf("instance id is empty")
	}
}

func TestLocalInstanceServiceCreateRecordsOperationAndIdempotency(t *testing.T) {
	orchestrator := &fakeInstanceOrchestrator{}
	operations := NewLocalOperationStore(WithOperationStoreClock(func() time.Time {
		return time.Unix(1000, 0)
	}))
	service := NewLocalInstanceServiceWithOptions(
		orchestrator,
		&fakeInstanceStore{},
		NewLocalInstanceOpsGuard(),
		WithOperationStore(operations),
	)
	request := ports.WorkloadInstanceCreateRequest{
		IdempotencyKey: "create-key-1",
		Spec: ports.WorkloadSpec{
			TenantID: "tenant-a",
			Name:     "app-01",
			Kind:     ports.WorkloadKindContainer,
			Image:    "harbor/app:1",
		},
		UserID:          "user-a",
		PermissionProof: "rbac:create:workload",
		RequestedAt:     time.Unix(900, 0),
	}

	first, err := service.Create(context.Background(), request)
	if err != nil {
		t.Fatalf("Create(first) error = %v", err)
	}
	if first.OperationID == "" {
		t.Fatalf("OperationID is empty")
	}
	second, err := service.Create(context.Background(), request)
	if err != nil {
		t.Fatalf("Create(second) error = %v", err)
	}
	if second.OperationID != first.OperationID {
		t.Fatalf("duplicate OperationID = %q, want %q", second.OperationID, first.OperationID)
	}
	if !second.IdempotentReplay {
		t.Fatalf("duplicate IdempotentReplay = false, want true")
	}
	if orchestrator.creates != 1 {
		t.Fatalf("creates = %d, want 1 after duplicate idempotency key", orchestrator.creates)
	}
	list, err := operations.ListOperations(context.Background(), ports.WorkloadOperationListRequest{
		TenantID:   "tenant-a",
		InstanceID: first.Ref.InstanceID,
	})
	if err != nil {
		t.Fatalf("ListOperations error = %v", err)
	}
	if len(list.Items) != 1 {
		t.Fatalf("operations = %d, want 1", len(list.Items))
	}
	if list.Items[0].Status != ports.WorkloadOperationSucceeded {
		t.Fatalf("operation status = %s, want succeeded", list.Items[0].Status)
	}
	if list.Items[0].InstanceID != first.Ref.InstanceID {
		t.Fatalf("operation instance id = %q, want %q", list.Items[0].InstanceID, first.Ref.InstanceID)
	}
	if len(list.Items[0].Steps) == 0 {
		t.Fatalf("operation steps are empty")
	}
}

func TestLocalInstanceServiceCreateIdempotencyInProgressDoesNotRecreate(t *testing.T) {
	operations := NewLocalOperationStore()
	existing, _, err := operations.RecordOperation(context.Background(), ports.WorkloadOperationRecord{
		TenantID:       "tenant-a",
		InstanceID:     "pending:operation-a",
		Operation:      ports.WorkloadLifecycleCreate,
		Status:         ports.WorkloadOperationInProgress,
		IdempotencyKey: "create-key-in-progress",
		RequestedBy:    "user-a",
	})
	if err != nil {
		t.Fatalf("RecordOperation error = %v", err)
	}
	orchestrator := &fakeInstanceOrchestrator{}
	service := NewLocalInstanceServiceWithOptions(
		orchestrator,
		&fakeInstanceStore{},
		NewLocalInstanceOpsGuard(),
		WithOperationStore(operations),
	)

	result, err := service.Create(context.Background(), ports.WorkloadInstanceCreateRequest{
		IdempotencyKey: "create-key-in-progress",
		Spec: ports.WorkloadSpec{
			TenantID: "tenant-a",
			Name:     "app-01",
			Kind:     ports.WorkloadKindContainer,
			Image:    "harbor/app:1",
		},
		UserID:          "user-a",
		PermissionProof: "rbac:create:workload",
	})
	if err != nil {
		t.Fatalf("Create duplicate in-progress error = %v", err)
	}
	if !result.IdempotentReplay || result.OperationID != existing.ID {
		t.Fatalf("result replay=%v op=%q, want replay op %q", result.IdempotentReplay, result.OperationID, existing.ID)
	}
	if orchestrator.creates != 0 {
		t.Fatalf("creates = %d, want 0 for in-progress idempotent replay", orchestrator.creates)
	}
}

func TestLocalInstanceServiceRejectsUnsupportedCreateKind(t *testing.T) {
	_, err := NewLocalInstanceService(&fakeInstanceOrchestrator{}, &fakeInstanceStore{}, NewLocalInstanceOpsGuard()).Create(context.Background(), ports.WorkloadInstanceCreateRequest{
		Spec: ports.WorkloadSpec{
			TenantID: "tenant-a",
			Name:     "batch-01",
			Kind:     ports.WorkloadKindBatchJob,
			Image:    "harbor/job:1",
		},
		UserID:          "user-a",
		PermissionProof: "rbac:create:workload",
	})
	if err == nil {
		t.Fatalf("Create() error = nil, want unsupported kind")
	}
	if !strings.Contains(err.Error(), "vm, container, and gpu_container") {
		t.Fatalf("error = %q, want supported kind list", err)
	}
}

func TestLocalInstanceServiceQueriesStore(t *testing.T) {
	store := &fakeInstanceStore{
		last: ports.WorkloadInstanceRecord{
			TenantID:   "tenant-a",
			InstanceID: "instance-a",
			Name:       "app-01",
			Kind:       ports.WorkloadKindContainer,
			Status: ports.WorkloadStatus{
				State: ports.WorkloadStateRunning,
			},
		},
	}
	service := NewLocalInstanceService(&fakeInstanceOrchestrator{}, store, NewLocalInstanceOpsGuard())
	record, err := service.Get(context.Background(), ports.WorkloadInstanceGetRequest{
		TenantID:   "tenant-a",
		InstanceID: "instance-a",
	})
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}
	if record.Status.State != ports.WorkloadStateRunning {
		t.Fatalf("state = %s, want running", record.Status.State)
	}
	records, err := service.List(context.Background(), ports.WorkloadInstanceListRequest{
		TenantID: "tenant-a",
		Kind:     ports.WorkloadKindContainer,
	})
	if err != nil {
		t.Fatalf("List() error = %v", err)
	}
	if len(records) != 1 {
		t.Fatalf("records = %d, want 1", len(records))
	}
}

func TestLocalInstanceServiceLifecycleOperationsUpdateStore(t *testing.T) {
	store := &fakeInstanceStore{
		last: ports.WorkloadInstanceRecord{
			TenantID:   "tenant-a",
			InstanceID: "instance-a",
			Name:       "app-01",
			Kind:       ports.WorkloadKindContainer,
			Status: ports.WorkloadStatus{
				State: ports.WorkloadStateStopped,
			},
		},
	}
	service := NewLocalInstanceService(&fakeInstanceOrchestrator{}, store, NewLocalInstanceOpsGuard())
	record, err := service.Start(context.Background(), ports.WorkloadInstanceLifecycleRequest{
		TenantID:        "tenant-a",
		InstanceID:      "instance-a",
		UserID:          "user-a",
		PermissionProof: "rbac:update:workload",
		RequestedAt:     time.Unix(800, 0),
	})
	if err != nil {
		t.Fatalf("Start() error = %v", err)
	}
	if record.Status.State != ports.WorkloadStateRunning {
		t.Fatalf("state = %s, want running", record.Status.State)
	}
	if store.upserts != 1 {
		t.Fatalf("upserts = %d, want 1", store.upserts)
	}

	record, err = service.Delete(context.Background(), ports.WorkloadInstanceLifecycleRequest{
		TenantID:        "tenant-a",
		InstanceID:      "instance-a",
		UserID:          "user-a",
		PermissionProof: "rbac:delete:workload",
	})
	if err != nil {
		t.Fatalf("Delete() error = %v", err)
	}
	if record.Status.State != ports.WorkloadStateDeleted {
		t.Fatalf("state = %s, want deleted", record.Status.State)
	}
}

func TestLocalInstanceServiceLifecycleRecordsOperation(t *testing.T) {
	store := &fakeInstanceStore{
		last: ports.WorkloadInstanceRecord{
			TenantID:   "tenant-a",
			InstanceID: "instance-a",
			Name:       "app-01",
			Kind:       ports.WorkloadKindContainer,
			Status: ports.WorkloadStatus{
				State: ports.WorkloadStateStopped,
			},
		},
	}
	operations := NewLocalOperationStore()
	service := NewLocalInstanceServiceWithOptions(
		&fakeInstanceOrchestrator{},
		store,
		NewLocalInstanceOpsGuard(),
		WithOperationStore(operations),
	)

	record, err := service.Start(context.Background(), ports.WorkloadInstanceLifecycleRequest{
		TenantID:        "tenant-a",
		InstanceID:      "instance-a",
		UserID:          "user-a",
		PermissionProof: "rbac:update:workload",
		RequestedAt:     time.Unix(1200, 0),
	})
	if err != nil {
		t.Fatalf("Start() error = %v", err)
	}
	if record.OperationID == "" {
		t.Fatalf("OperationID is empty")
	}
	operation, err := operations.GetOperation(context.Background(), "tenant-a", record.OperationID)
	if err != nil {
		t.Fatalf("GetOperation error = %v", err)
	}
	if operation.Operation != ports.WorkloadLifecycleStart || operation.Status != ports.WorkloadOperationSucceeded {
		t.Fatalf("operation=%s status=%s, want start/succeeded", operation.Operation, operation.Status)
	}
	if len(operation.Steps) == 0 {
		t.Fatalf("operation steps are empty")
	}
	resized, err := service.Resize(context.Background(), ports.WorkloadInstanceResizeRequest{
		IdempotencyKey:  "resize-key-1",
		TenantID:        "tenant-a",
		InstanceID:      "instance-a",
		Resources:       ports.WorkloadResourceRequest{CPU: "4", Memory: "8Gi"},
		UserID:          "user-a",
		PermissionProof: "rbac:update:workload",
		RequestedAt:     time.Unix(1300, 0),
	})
	if err != nil {
		t.Fatalf("Resize() error = %v", err)
	}
	duplicate, err := service.Resize(context.Background(), ports.WorkloadInstanceResizeRequest{
		IdempotencyKey:  "resize-key-1",
		TenantID:        "tenant-a",
		InstanceID:      "instance-a",
		Resources:       ports.WorkloadResourceRequest{CPU: "4", Memory: "8Gi"},
		UserID:          "user-a",
		PermissionProof: "rbac:update:workload",
		RequestedAt:     time.Unix(1301, 0),
	})
	if err != nil {
		t.Fatalf("Resize(duplicate) error = %v", err)
	}
	if duplicate.OperationID != resized.OperationID {
		t.Fatalf("duplicate resize operation id = %q, want %q", duplicate.OperationID, resized.OperationID)
	}
	list, err := operations.ListOperations(context.Background(), ports.WorkloadOperationListRequest{
		TenantID:   "tenant-a",
		InstanceID: "instance-a",
	})
	if err != nil {
		t.Fatalf("ListOperations error = %v", err)
	}
	if len(list.Items) != 2 {
		t.Fatalf("operations = %d, want start + resize only", len(list.Items))
	}
}

func TestLocalInstanceServiceLifecycleUsesProviderExecutor(t *testing.T) {
	store := &fakeInstanceStore{
		last: ports.WorkloadInstanceRecord{
			TenantID:     "tenant-a",
			InstanceID:   "instance-a",
			Name:         "app-01",
			Kind:         ports.WorkloadKindContainer,
			Provider:     "kubernetes",
			ResourceRefs: []string{"kubernetes/Deployment/app-01"},
			Status: ports.WorkloadStatus{
				State: ports.WorkloadStateStopped,
			},
		},
	}
	lifecycle := &fakeLifecycleExecutor{}
	service := NewLocalInstanceServiceWithOptions(
		&fakeInstanceOrchestrator{},
		store,
		NewLocalInstanceOpsGuard(),
		WithInstanceLifecycleExecutor(lifecycle),
	)

	record, err := service.Start(context.Background(), ports.WorkloadInstanceLifecycleRequest{
		TenantID:        "tenant-a",
		InstanceID:      "instance-a",
		UserID:          "user-a",
		PermissionProof: "rbac:update:workload",
	})
	if err != nil {
		t.Fatalf("Start() error = %v", err)
	}
	if lifecycle.calls != 1 || lifecycle.action != ports.WorkloadLifecycleStart {
		t.Fatalf("lifecycle calls=%d action=%s, want start", lifecycle.calls, lifecycle.action)
	}
	if record.Status.State != ports.WorkloadStateRunning {
		t.Fatalf("state = %s, want running", record.Status.State)
	}
}

func TestLocalInstanceServiceOpsUsesOpsGuard(t *testing.T) {
	store := &fakeInstanceStore{
		last: ports.WorkloadInstanceRecord{
			TenantID:   "tenant-a",
			InstanceID: "instance-a",
			Name:       "app-01",
			Kind:       ports.WorkloadKindContainer,
			Status: ports.WorkloadStatus{
				State: ports.WorkloadStateRunning,
			},
		},
	}
	service := NewLocalInstanceService(&fakeInstanceOrchestrator{}, store, NewLocalInstanceOpsGuard())
	result, err := service.Ops(context.Background(), ports.WorkloadInstanceOpsRequest{
		TenantID:        "tenant-a",
		InstanceID:      "instance-a",
		Action:          ports.WorkloadInstanceOpsLogs,
		UserID:          "user-a",
		PermissionProof: "rbac:read:workload",
	})
	if err != nil {
		t.Fatalf("Ops() error = %v", err)
	}
	if result.Accepted {
		t.Fatalf("Accepted = true, want disabled ops guard")
	}
	if !strings.Contains(result.Reason, "disabled") {
		t.Fatalf("Reason = %q, want disabled", result.Reason)
	}
}

func TestLocalInstanceServiceVMConsoleOpsCreatesSession(t *testing.T) {
	store := &fakeInstanceStore{
		last: ports.WorkloadInstanceRecord{
			TenantID:   "tenant-a",
			InstanceID: "instance-a",
			Name:       "vm-01",
			Kind:       ports.WorkloadKindVM,
			Status: ports.WorkloadStatus{
				State: ports.WorkloadStateRunning,
			},
		},
	}
	service := NewLocalInstanceService(&fakeInstanceOrchestrator{}, store, NewLocalInstanceOpsGuard(WithInstanceOpsEnabled(true)))
	result, err := service.Ops(context.Background(), ports.WorkloadInstanceOpsRequest{
		TenantID:        "tenant-a",
		InstanceID:      "instance-a",
		Action:          ports.WorkloadInstanceOpsVMVNC,
		UserID:          "user-a",
		PermissionProof: "rbac:console:workload",
	})
	if err != nil {
		t.Fatalf("Ops(vm_vnc) error = %v", err)
	}
	if !result.Accepted || result.Protocol != "vnc" || result.ConnectURL == "" {
		t.Fatalf("result accepted=%v protocol=%q connect=%q, want vnc session", result.Accepted, result.Protocol, result.ConnectURL)
	}
}

type fakeInstanceOrchestrator struct {
	creates int
}

func (o *fakeInstanceOrchestrator) Create(_ context.Context, request ports.WorkloadInstanceCreateRequest) (ports.WorkloadInstanceCreateResult, error) {
	o.creates++
	return ports.WorkloadInstanceCreateResult{
		Ref: ports.WorkloadRef{
			TenantID:   request.Spec.TenantID,
			InstanceID: "instance-a",
			Kind:       request.Spec.Kind,
		},
		FinalStatus: ports.WorkloadStatus{
			State:     ports.WorkloadStateRunning,
			UpdatedAt: time.Unix(950, 0),
		},
		Admission: ports.WorkloadAdmissionResult{
			Allowed: true,
			Reason:  "accepted",
		},
		DryRun: ports.WorkloadProviderDryRunResult{
			Accepted: true,
			Reason:   "accepted",
		},
		Apply: ports.WorkloadProviderApplyResult{
			Applied:      true,
			Reason:       "applied",
			ResourceRefs: []string{"kubernetes/Deployment/app-01"},
		},
		Observation:  ports.WorkloadProviderObservation{Provider: "kubernetes", Phase: "Running"},
		Reconcile:    ports.WorkloadReconcileResult{Changed: true, Reason: "state reconciled"},
		Orchestrated: true,
	}, nil
}

var _ ports.WorkloadInstanceOrchestrator = (*fakeInstanceOrchestrator)(nil)

type fakeLifecycleExecutor struct {
	calls  int
	action ports.WorkloadLifecycleAction
}

func (e *fakeLifecycleExecutor) Apply(_ context.Context, request ports.WorkloadInstanceLifecycleRequest, _ ports.WorkloadInstanceRecord) (ports.WorkloadInstanceLifecycleResult, error) {
	e.calls++
	e.action = request.Action
	return ports.WorkloadInstanceLifecycleResult{
		Action:   request.Action,
		Accepted: true,
	}, nil
}

var _ ports.WorkloadInstanceLifecycleExecutor = (*fakeLifecycleExecutor)(nil)
