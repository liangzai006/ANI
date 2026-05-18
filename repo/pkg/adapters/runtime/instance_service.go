package runtime

import (
	"context"
	"fmt"
	"strings"

	"github.com/google/uuid"
	"github.com/kubercloud/ani/pkg/ports"
)

type LocalInstanceService struct {
	orchestrator ports.WorkloadInstanceOrchestrator
	store        ports.WorkloadInstanceStore
	operations   ports.WorkloadOperationStore
	lifecycle    ports.WorkloadInstanceLifecycleExecutor
	ops          ports.WorkloadInstanceOps
}

type InstanceServiceOption func(*LocalInstanceService)

func WithInstanceLifecycleExecutor(lifecycle ports.WorkloadInstanceLifecycleExecutor) InstanceServiceOption {
	return func(service *LocalInstanceService) {
		service.lifecycle = lifecycle
	}
}

func WithOperationStore(operations ports.WorkloadOperationStore) InstanceServiceOption {
	return func(service *LocalInstanceService) {
		service.operations = operations
	}
}

func NewLocalInstanceService(orchestrator ports.WorkloadInstanceOrchestrator, store ports.WorkloadInstanceStore, ops ports.WorkloadInstanceOps) *LocalInstanceService {
	return &LocalInstanceService{
		orchestrator: orchestrator,
		store:        store,
		ops:          ops,
	}
}

func NewLocalInstanceServiceWithOptions(orchestrator ports.WorkloadInstanceOrchestrator, store ports.WorkloadInstanceStore, ops ports.WorkloadInstanceOps, options ...InstanceServiceOption) *LocalInstanceService {
	service := NewLocalInstanceService(orchestrator, store, ops)
	for _, option := range options {
		option(service)
	}
	return service
}

func (s *LocalInstanceService) Create(ctx context.Context, request ports.WorkloadInstanceCreateRequest) (ports.WorkloadInstanceCreateResult, error) {
	if s.orchestrator == nil {
		return ports.WorkloadInstanceCreateResult{}, ports.ErrNotConfigured
	}
	if strings.TrimSpace(request.Spec.TenantID) == "" {
		return ports.WorkloadInstanceCreateResult{}, fmt.Errorf("%w: tenantID is required", ports.ErrInvalid)
	}
	if request.Spec.Kind != ports.WorkloadKindVM &&
		request.Spec.Kind != ports.WorkloadKindContainer &&
		request.Spec.Kind != ports.WorkloadKindGPUContainer {
		return ports.WorkloadInstanceCreateResult{}, fmt.Errorf("%w: instance service supports vm, container, and gpu_container create", ports.ErrUnsupported)
	}
	if strings.TrimSpace(request.UserID) == "" {
		return ports.WorkloadInstanceCreateResult{}, fmt.Errorf("%w: user id is required", ports.ErrInvalid)
	}
	if strings.TrimSpace(request.PermissionProof) == "" {
		return ports.WorkloadInstanceCreateResult{}, fmt.Errorf("%w: permission proof is required", ports.ErrInvalid)
	}
	var operation ports.WorkloadOperationRecord
	preRecorded := false
	if s.operations != nil && strings.TrimSpace(request.IdempotencyKey) != "" {
		opID := uuid.NewString()
		var existing bool
		var err error
		operation, existing, err = s.operations.RecordOperation(ctx, ports.WorkloadOperationRecord{
			ID:             opID,
			TenantID:       request.Spec.TenantID,
			InstanceID:     pendingOperationInstanceID(opID),
			Operation:      ports.WorkloadLifecycleCreate,
			Status:         ports.WorkloadOperationInProgress,
			IdempotencyKey: request.IdempotencyKey,
			RequestedBy:    request.UserID,
			Precheck:       map[string]any{"allowed": true},
			AfterSpec:      workloadSpecSummary(request.Spec),
			CreatedAt:      firstNonZeroTime(request.RequestedAt),
			UpdatedAt:      firstNonZeroTime(request.RequestedAt),
		})
		if err != nil {
			return ports.WorkloadInstanceCreateResult{}, err
		}
		if existing {
			return ports.WorkloadInstanceCreateResult{
				Ref: ports.WorkloadRef{
					TenantID:   operation.TenantID,
					InstanceID: operation.InstanceID,
					Kind:       request.Spec.Kind,
				},
				OperationID:      operation.ID,
				IdempotentReplay: true,
			}, nil
		}
		preRecorded = true
	}
	result, err := s.orchestrator.Create(ctx, request)
	if err != nil {
		if preRecorded {
			_, _ = s.operations.UpdateOperation(ctx, operation.ID, ports.WorkloadOperationUpdate{
				Status:         ports.WorkloadOperationFailed,
				FailureReason:  "create_failed",
				FailureMessage: err.Error(),
				RetryEligible:  true,
				UpdatedAt:      firstNonZeroTime(request.RequestedAt),
			})
		}
		return ports.WorkloadInstanceCreateResult{}, err
	}
	if s.operations == nil {
		return result, nil
	}
	if !preRecorded {
		operation, _, err = s.operations.RecordOperation(ctx, ports.WorkloadOperationRecord{
			TenantID:       result.Ref.TenantID,
			InstanceID:     result.Ref.InstanceID,
			Operation:      ports.WorkloadLifecycleCreate,
			Status:         ports.WorkloadOperationInProgress,
			IdempotencyKey: request.IdempotencyKey,
			RequestedBy:    request.UserID,
			Precheck:       map[string]any{"allowed": true},
			AfterSpec:      workloadSpecSummary(request.Spec),
			ProviderRefs:   result.Apply.ResourceRefs,
			CreatedAt:      firstNonZeroTime(request.RequestedAt),
			UpdatedAt:      firstNonZeroTime(request.RequestedAt),
		})
		if err != nil {
			return ports.WorkloadInstanceCreateResult{}, err
		}
	}
	result.OperationID = operation.ID
	if err := s.recordCreateTimeline(ctx, operation.ID, result); err != nil {
		return ports.WorkloadInstanceCreateResult{}, err
	}
	if _, err := s.operations.UpdateOperation(ctx, operation.ID, ports.WorkloadOperationUpdate{
		InstanceID:   result.Ref.InstanceID,
		Status:       ports.WorkloadOperationSucceeded,
		ProviderRefs: result.Apply.ResourceRefs,
		UpdatedAt:    firstNonZeroTime(result.FinalStatus.UpdatedAt, request.RequestedAt),
	}); err != nil {
		return ports.WorkloadInstanceCreateResult{}, err
	}
	return result, nil
}

func (s *LocalInstanceService) Get(ctx context.Context, request ports.WorkloadInstanceGetRequest) (ports.WorkloadInstanceRecord, error) {
	if s.store == nil {
		return ports.WorkloadInstanceRecord{}, ports.ErrNotConfigured
	}
	if strings.TrimSpace(request.TenantID) == "" {
		return ports.WorkloadInstanceRecord{}, fmt.Errorf("%w: tenantID is required", ports.ErrInvalid)
	}
	if strings.TrimSpace(request.InstanceID) == "" {
		return ports.WorkloadInstanceRecord{}, fmt.Errorf("%w: instanceID is required", ports.ErrInvalid)
	}
	return s.store.Get(ctx, request.TenantID, request.InstanceID)
}

func (s *LocalInstanceService) List(ctx context.Context, request ports.WorkloadInstanceListRequest) ([]ports.WorkloadInstanceRecord, error) {
	if s.store == nil {
		return nil, ports.ErrNotConfigured
	}
	if strings.TrimSpace(request.TenantID) == "" {
		return nil, fmt.Errorf("%w: tenantID is required", ports.ErrInvalid)
	}
	return s.store.List(ctx, request.TenantID, request.Kind)
}

func (s *LocalInstanceService) Start(ctx context.Context, request ports.WorkloadInstanceLifecycleRequest) (ports.WorkloadInstanceRecord, error) {
	request.Action = ports.WorkloadLifecycleStart
	return s.applyLifecycle(ctx, request)
}

func (s *LocalInstanceService) Stop(ctx context.Context, request ports.WorkloadInstanceLifecycleRequest) (ports.WorkloadInstanceRecord, error) {
	request.Action = ports.WorkloadLifecycleStop
	return s.applyLifecycle(ctx, request)
}

func (s *LocalInstanceService) Restart(ctx context.Context, request ports.WorkloadInstanceLifecycleRequest) (ports.WorkloadInstanceRecord, error) {
	request.Action = ports.WorkloadLifecycleRestart
	return s.applyLifecycle(ctx, request)
}

func (s *LocalInstanceService) Resize(ctx context.Context, request ports.WorkloadInstanceResizeRequest) (ports.WorkloadInstanceRecord, error) {
	lifecycle := ports.WorkloadInstanceLifecycleRequest{
		IdempotencyKey:  request.IdempotencyKey,
		TenantID:        request.TenantID,
		InstanceID:      request.InstanceID,
		Action:          ports.WorkloadLifecycleResize,
		UserID:          request.UserID,
		PermissionProof: request.PermissionProof,
		RequestedAt:     request.RequestedAt,
	}
	return s.applyLifecycle(ctx, lifecycle)
}

func (s *LocalInstanceService) Delete(ctx context.Context, request ports.WorkloadInstanceLifecycleRequest) (ports.WorkloadInstanceRecord, error) {
	request.Action = ports.WorkloadLifecycleDelete
	return s.applyLifecycle(ctx, request)
}

func (s *LocalInstanceService) Ops(ctx context.Context, request ports.WorkloadInstanceOpsRequest) (ports.WorkloadInstanceOpsResult, error) {
	if s.store == nil || s.ops == nil {
		return ports.WorkloadInstanceOpsResult{}, ports.ErrNotConfigured
	}
	record, err := s.Get(ctx, ports.WorkloadInstanceGetRequest{
		TenantID:   request.TenantID,
		InstanceID: request.InstanceID,
	})
	if err != nil {
		return ports.WorkloadInstanceOpsResult{}, err
	}
	return s.ops.Run(ctx, request, record)
}

func (s *LocalInstanceService) applyLifecycle(ctx context.Context, request ports.WorkloadInstanceLifecycleRequest) (ports.WorkloadInstanceRecord, error) {
	if s.store == nil {
		return ports.WorkloadInstanceRecord{}, ports.ErrNotConfigured
	}
	if strings.TrimSpace(request.TenantID) == "" || strings.TrimSpace(request.InstanceID) == "" {
		return ports.WorkloadInstanceRecord{}, fmt.Errorf("%w: tenantID and instanceID are required", ports.ErrInvalid)
	}
	if strings.TrimSpace(request.UserID) == "" || strings.TrimSpace(request.PermissionProof) == "" {
		return ports.WorkloadInstanceRecord{}, fmt.Errorf("%w: user id and permission proof are required", ports.ErrInvalid)
	}
	record, err := s.store.Get(ctx, request.TenantID, request.InstanceID)
	if err != nil {
		return ports.WorkloadInstanceRecord{}, err
	}
	if s.operations != nil {
		if strings.TrimSpace(request.IdempotencyKey) != "" {
			existing, err := s.operations.GetOperationByIdempotencyKey(ctx, request.TenantID, request.IdempotencyKey)
			if err == nil {
				record.OperationID = existing.ID
				return record, nil
			}
		}
	}
	next, err := transition(record.Status.State, request.Action)
	if err != nil {
		return ports.WorkloadInstanceRecord{}, err
	}
	opID := ""
	if s.operations != nil {
		operation, existing, err := s.operations.RecordOperation(ctx, ports.WorkloadOperationRecord{
			TenantID:       request.TenantID,
			InstanceID:     request.InstanceID,
			Operation:      request.Action,
			Status:         ports.WorkloadOperationInProgress,
			IdempotencyKey: request.IdempotencyKey,
			RequestedBy:    request.UserID,
			Precheck:       map[string]any{"allowed": true, "from_state": string(record.Status.State), "to_state": string(next)},
			BeforeSpec:     workloadRecordSummary(record),
			CreatedAt:      request.RequestedAt,
			UpdatedAt:      request.RequestedAt,
		})
		if err != nil {
			return ports.WorkloadInstanceRecord{}, err
		}
		opID = operation.ID
		if existing {
			record.OperationID = opID
			return record, nil
		}
		if _, err := s.operations.AddOperationStep(ctx, opID, ports.WorkloadOperationStep{
			StepName: "precheck",
			Status:   ports.WorkloadOperationStepSucceeded,
			Message:  "lifecycle transition accepted",
		}); err != nil {
			return ports.WorkloadInstanceRecord{}, err
		}
	}
	if s.lifecycle != nil {
		result, err := s.lifecycle.Apply(ctx, request, record)
		if err != nil {
			if opID != "" {
				_, _ = s.operations.UpdateOperation(ctx, opID, ports.WorkloadOperationUpdate{
					Status:         ports.WorkloadOperationFailed,
					FailureReason:  "provider_lifecycle_failed",
					FailureMessage: err.Error(),
					RetryEligible:  true,
					UpdatedAt:      request.RequestedAt,
				})
			}
			return ports.WorkloadInstanceRecord{}, err
		}
		if result.OperationID != "" {
			opID = result.OperationID
		}
		if !result.Accepted {
			record.Status.Reason = result.Reason
			if !result.CheckedAt.IsZero() {
				record.Status.UpdatedAt = result.CheckedAt.UTC()
				record.UpdatedAt = result.CheckedAt.UTC()
			}
			if err := s.store.UpsertStatus(ctx, record); err != nil {
				return ports.WorkloadInstanceRecord{}, err
			}
			record.OperationID = opID
			if opID != "" {
				_, _ = s.operations.UpdateOperation(ctx, opID, ports.WorkloadOperationUpdate{
					Status:         ports.WorkloadOperationFailed,
					FailureReason:  "provider_lifecycle_rejected",
					FailureMessage: result.Reason,
					RetryEligible:  true,
					UpdatedAt:      record.UpdatedAt,
				})
			}
			return record, nil
		}
	}
	record.Status.State = next
	record.Status.Reason = "lifecycle " + string(request.Action) + " requested"
	if !request.RequestedAt.IsZero() {
		record.Status.UpdatedAt = request.RequestedAt.UTC()
		record.UpdatedAt = request.RequestedAt.UTC()
	}
	if err := s.store.UpsertStatus(ctx, record); err != nil {
		return ports.WorkloadInstanceRecord{}, err
	}
	record.OperationID = opID
	if opID != "" {
		if _, err := s.operations.AddOperationStep(ctx, opID, ports.WorkloadOperationStep{
			StepName: "apply_lifecycle",
			Status:   ports.WorkloadOperationStepSucceeded,
			Message:  "lifecycle " + string(request.Action) + " accepted",
		}); err != nil {
			return ports.WorkloadInstanceRecord{}, err
		}
		if _, err := s.operations.UpdateOperation(ctx, opID, ports.WorkloadOperationUpdate{
			Status:       ports.WorkloadOperationSucceeded,
			UpdatedAt:    record.UpdatedAt,
			ProviderRefs: record.ResourceRefs,
		}); err != nil {
			return ports.WorkloadInstanceRecord{}, err
		}
	}
	return record, nil
}

var _ ports.WorkloadInstanceService = (*LocalInstanceService)(nil)

func (s *LocalInstanceService) recordCreateTimeline(ctx context.Context, operationID string, result ports.WorkloadInstanceCreateResult) error {
	steps := []ports.WorkloadOperationStep{
		{StepName: "plan", Status: ports.WorkloadOperationStepSucceeded, Message: "workload reference allocated"},
		{StepName: "render", Status: ports.WorkloadOperationStepSucceeded, Message: fmt.Sprintf("%d provider manifest(s) rendered", len(result.Manifests))},
		{StepName: "admission", Status: boolStepStatus(result.Admission.Allowed), Message: result.Admission.Reason},
		{StepName: "audit", Status: nonEmptyStepStatus(result.AuditID), Message: "plan audit recorded"},
		{StepName: "dry_run", Status: boolStepStatus(result.DryRun.Accepted), Message: result.DryRun.Reason},
		{StepName: "apply", Status: applyStepStatus(result.Apply.Applied), Message: result.Apply.Reason},
	}
	if result.Apply.Applied {
		steps = append(steps,
			ports.WorkloadOperationStep{StepName: "observe", Status: nonEmptyStepStatus(result.Observation.Provider), Message: result.Observation.Phase},
			ports.WorkloadOperationStep{StepName: "reconcile", Status: boolStepStatus(result.Reconcile.Changed || result.Orchestrated), Message: result.Reconcile.Reason},
		)
	}
	for _, step := range steps {
		if _, err := s.operations.AddOperationStep(ctx, operationID, step); err != nil {
			return err
		}
	}
	return nil
}

func boolStepStatus(ok bool) ports.WorkloadOperationStepStatus {
	if ok {
		return ports.WorkloadOperationStepSucceeded
	}
	return ports.WorkloadOperationStepFailed
}

func nonEmptyStepStatus(value string) ports.WorkloadOperationStepStatus {
	if strings.TrimSpace(value) == "" {
		return ports.WorkloadOperationStepSkipped
	}
	return ports.WorkloadOperationStepSucceeded
}

func applyStepStatus(applied bool) ports.WorkloadOperationStepStatus {
	if applied {
		return ports.WorkloadOperationStepSucceeded
	}
	return ports.WorkloadOperationStepSkipped
}

func workloadSpecSummary(spec ports.WorkloadSpec) map[string]any {
	return map[string]any{
		"tenant_id": spec.TenantID,
		"name":      spec.Name,
		"kind":      string(spec.Kind),
		"image":     spec.Image,
		"cpu":       spec.Resources.CPU,
		"memory":    spec.Resources.Memory,
		"gpu_count": spec.Resources.GPU.RequiredCount,
	}
}

func workloadRecordSummary(record ports.WorkloadInstanceRecord) map[string]any {
	return map[string]any{
		"tenant_id":   record.TenantID,
		"instance_id": record.InstanceID,
		"name":        record.Name,
		"kind":        string(record.Kind),
		"state":       string(record.Status.State),
		"provider":    record.Provider,
	}
}

func pendingOperationInstanceID(operationID string) string {
	return "pending:" + operationID
}
