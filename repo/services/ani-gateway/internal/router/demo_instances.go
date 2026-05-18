package router

import (
	"bytes"
	"context"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/cloudwego/hertz/pkg/app"
	"github.com/cloudwego/hertz/pkg/route"
	runtimeadapter "github.com/kubercloud/ani/pkg/adapters/runtime"
	"github.com/kubercloud/ani/pkg/ports"
	"github.com/kubercloud/ani/services/ani-gateway/internal/middleware"
)

type demoInstanceStore struct {
	mu      sync.RWMutex
	records map[string]ports.WorkloadInstanceRecord
}

func newDemoInstanceStore() *demoInstanceStore {
	return &demoInstanceStore{records: map[string]ports.WorkloadInstanceRecord{}}
}

func (s *demoInstanceStore) UpsertStatus(_ context.Context, record ports.WorkloadInstanceRecord) error {
	if strings.TrimSpace(record.TenantID) == "" || strings.TrimSpace(record.InstanceID) == "" {
		return fmt.Errorf("%w: tenantID and instanceID are required", ports.ErrInvalid)
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.records[record.TenantID+"/"+record.InstanceID] = record
	return nil
}

func (s *demoInstanceStore) Get(_ context.Context, tenantID string, instanceID string) (ports.WorkloadInstanceRecord, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	record, ok := s.records[tenantID+"/"+instanceID]
	if !ok {
		return ports.WorkloadInstanceRecord{}, ports.ErrNotFound
	}
	return record, nil
}

func (s *demoInstanceStore) List(_ context.Context, tenantID string, kind ports.WorkloadKind) ([]ports.WorkloadInstanceRecord, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	records := make([]ports.WorkloadInstanceRecord, 0, len(s.records))
	for _, record := range s.records {
		if record.TenantID != tenantID {
			continue
		}
		if kind != "" && record.Kind != kind {
			continue
		}
		records = append(records, record)
	}
	sort.Slice(records, func(i, j int) bool {
		return records[i].CreatedAt.After(records[j].CreatedAt)
	})
	return records, nil
}

var _ ports.WorkloadInstanceStore = (*demoInstanceStore)(nil)

type demoInstanceAPI struct {
	service    ports.WorkloadInstanceService
	operations ports.WorkloadOperationStore
}

type demoCreateInstanceRequest struct {
	Kind           string `json:"kind"`
	Name           string `json:"name"`
	CPU            string `json:"cpu"`
	Memory         string `json:"memory"`
	BootImage      string `json:"boot_image"`
	Image          string `json:"image"`
	GPUVendor      string `json:"gpu_vendor"`
	GPUModel       string `json:"gpu_model"`
	GPUCount       int    `json:"gpu_count"`
	AutoStart      *bool  `json:"auto_start"`
	Description    string `json:"description"`
	IdempotencyKey string `json:"idempotency_key"`
}

type demoLifecycleRequest struct {
	Action         string `json:"action"`
	CPU            string `json:"cpu"`
	Memory         string `json:"memory"`
	IdempotencyKey string `json:"idempotency_key"`
}

type demoConsoleRequest struct {
	Protocol string `json:"protocol"`
}

type demoShellExecRequest struct {
	Command string `json:"command"`
}

type demoShellExecResponse struct {
	Command  string `json:"command"`
	Output   string `json:"output"`
	ExitCode int    `json:"exit_code"`
	CWD      string `json:"cwd"`
}

type demoInstanceResponse struct {
	ID           string   `json:"id"`
	TenantID     string   `json:"tenant_id"`
	Name         string   `json:"name"`
	Kind         string   `json:"kind"`
	Status       string   `json:"status"`
	Provider     string   `json:"provider"`
	OperationID  string   `json:"operation_id,omitempty"`
	ResourceRefs []string `json:"resource_refs"`
	Endpoint     string   `json:"endpoint"`
	CreatedAt    string   `json:"created_at"`
	UpdatedAt    string   `json:"updated_at"`
}

type demoInstanceCreateResponse struct {
	Instance    demoInstanceResponse `json:"instance"`
	OperationID string               `json:"operation_id"`
	AuditID     string               `json:"audit_id"`
	Manifests   []demoManifest       `json:"manifests"`
	Timeline    []demoTimelineStep   `json:"timeline"`
	DemoNotice  string               `json:"demo_notice"`
}

type demoOperationResponse struct {
	ID             string             `json:"id"`
	TenantID       string             `json:"tenant_id"`
	InstanceID     string             `json:"instance_id"`
	Operation      string             `json:"operation"`
	Status         string             `json:"status"`
	IdempotencyKey string             `json:"idempotency_key,omitempty"`
	RequestedBy    string             `json:"requested_by"`
	FailureReason  string             `json:"failure_reason,omitempty"`
	FailureMessage string             `json:"failure_message,omitempty"`
	RetryEligible  bool               `json:"retry_eligible"`
	Steps          []demoTimelineStep `json:"steps"`
	CreatedAt      string             `json:"created_at"`
	UpdatedAt      string             `json:"updated_at"`
}

type demoManifest struct {
	Name     string `json:"name"`
	Kind     string `json:"kind"`
	Provider string `json:"provider"`
	Content  string `json:"content"`
}

type demoTimelineStep struct {
	Name   string `json:"name"`
	Status string `json:"status"`
	Detail string `json:"detail"`
}

func newDemoInstanceAPI() *demoInstanceAPI {
	store := newDemoInstanceStore()
	operations := runtimeadapter.NewLocalOperationStore()
	planner := runtimeadapter.NewPlanningRuntime(runtimeadapter.WithGPUInventory(demoGPUInventory{}))
	orchestrator := runtimeadapter.NewLocalInstanceOrchestrator(
		planner,
		runtimeadapter.NewKubernetesDryRunRenderer(planner),
		runtimeadapter.NewLocalAdmissionGuard(),
		&demoPlanAuditStore{},
		runtimeadapter.NewLocalProviderDryRun(),
		runtimeadapter.NewLocalProviderApply(runtimeadapter.WithProviderApplyEnabled(true)),
		runtimeadapter.NewLocalProviderStatusReader(),
		runtimeadapter.NewLocalStatusReconciler(),
		runtimeadapter.WithInstanceStore(store),
	)
	service := runtimeadapter.NewLocalInstanceServiceWithOptions(
		orchestrator,
		store,
		runtimeadapter.NewLocalInstanceOpsGuard(runtimeadapter.WithInstanceOpsEnabled(true)),
		runtimeadapter.WithOperationStore(operations),
	)
	return &demoInstanceAPI{service: service, operations: operations}
}

func registerDemoInstances(v1 *route.RouterGroup) {
	api := newDemoInstanceAPI()
	v1.GET("/demo/instances", api.list)
	v1.POST("/demo/instances", api.create)
	v1.GET("/demo/instances/:instance_id", api.get)
	v1.GET("/demo/instances/:instance_id/operations", api.listOperations)
	v1.POST("/demo/instances/:instance_id/lifecycle", api.lifecycle)
	v1.GET("/demo/instances/:instance_id/ops/:action", api.ops)
	v1.POST("/demo/instances/:instance_id/console", api.console)
	v1.POST("/demo/instances/:instance_id/console/exec", api.consoleExec)
	v1.GET("/instances/:instance_id/operations", api.listOperations)
	v1.GET("/instance-operations/:operation_id", api.getOperation)
}

func (api *demoInstanceAPI) create(ctx context.Context, c *app.RequestContext) {
	var req demoCreateInstanceRequest
	if err := c.BindJSON(&req); err != nil {
		writeDemoError(c, http.StatusBadRequest, "BAD_REQUEST", "invalid instance request")
		return
	}
	spec, err := demoSpecFromRequest(req, demoTenantID(c))
	if err != nil {
		writeDemoError(c, http.StatusBadRequest, "BAD_REQUEST", err.Error())
		return
	}
	result, err := api.service.Create(ctx, ports.WorkloadInstanceCreateRequest{
		IdempotencyKey:  req.IdempotencyKey,
		Spec:            spec,
		UserID:          demoUserID(c),
		PermissionProof: "demo:instance:create",
		RequestedAt:     time.Now().UTC(),
	})
	if err != nil {
		writeDemoError(c, http.StatusBadRequest, "INSTANCE_CREATE_FAILED", err.Error())
		return
	}
	if result.IdempotentReplay && strings.HasPrefix(result.Ref.InstanceID, "pending:") {
		c.JSON(http.StatusConflict, map[string]any{
			"code":         "IDEMPOTENT_REPLAY_IN_PROGRESS",
			"message":      "request is already accepted and still in progress",
			"operation_id": result.OperationID,
		})
		return
	}
	record, err := api.service.Get(ctx, ports.WorkloadInstanceGetRequest{
		TenantID:   result.Ref.TenantID,
		InstanceID: result.Ref.InstanceID,
	})
	if err != nil {
		writeDemoError(c, http.StatusInternalServerError, "INSTANCE_LOOKUP_FAILED", err.Error())
		return
	}
	status := http.StatusCreated
	if result.IdempotentReplay {
		status = http.StatusConflict
	}
	c.JSON(status, demoInstanceCreateResponse{
		Instance:    demoInstanceFromRecord(record),
		OperationID: result.OperationID,
		AuditID:     result.AuditID,
		Manifests:   demoManifests(result.Manifests),
		Timeline:    demoTimeline(result),
		DemoNotice:  "demo profile uses the M1 instance service with local apply enabled; set kubernetes_rest provider separately for live cluster execution.",
	})
}

func (api *demoInstanceAPI) get(ctx context.Context, c *app.RequestContext) {
	record, err := api.service.Get(ctx, ports.WorkloadInstanceGetRequest{
		TenantID:   demoTenantID(c),
		InstanceID: c.Param("instance_id"),
	})
	if err != nil {
		writeDemoError(c, http.StatusNotFound, "INSTANCE_NOT_FOUND", err.Error())
		return
	}
	c.JSON(http.StatusOK, demoInstanceFromRecord(record))
}

func (api *demoInstanceAPI) list(ctx context.Context, c *app.RequestContext) {
	kind := ports.WorkloadKind(c.Query("kind"))
	records, err := api.service.List(ctx, ports.WorkloadInstanceListRequest{
		TenantID: demoTenantID(c),
		Kind:     kind,
	})
	if err != nil {
		writeDemoError(c, http.StatusBadRequest, "INSTANCE_LIST_FAILED", err.Error())
		return
	}
	items := make([]demoInstanceResponse, 0, len(records))
	for _, record := range records {
		items = append(items, demoInstanceFromRecord(record))
	}
	c.JSON(http.StatusOK, map[string]any{"items": items, "total": len(items)})
}

func (api *demoInstanceAPI) lifecycle(ctx context.Context, c *app.RequestContext) {
	var req demoLifecycleRequest
	if err := c.BindJSON(&req); err != nil {
		writeDemoError(c, http.StatusBadRequest, "BAD_REQUEST", "invalid lifecycle request")
		return
	}
	lifecycle := ports.WorkloadInstanceLifecycleRequest{
		IdempotencyKey:  req.IdempotencyKey,
		TenantID:        demoTenantID(c),
		InstanceID:      c.Param("instance_id"),
		UserID:          demoUserID(c),
		PermissionProof: "demo:instance:lifecycle",
		RequestedAt:     time.Now().UTC(),
	}
	var (
		record ports.WorkloadInstanceRecord
		err    error
	)
	switch strings.ToLower(strings.TrimSpace(req.Action)) {
	case "start":
		record, err = api.service.Start(ctx, lifecycle)
	case "stop":
		record, err = api.service.Stop(ctx, lifecycle)
	case "restart":
		record, err = api.service.Restart(ctx, lifecycle)
	case "resize":
		record, err = api.service.Resize(ctx, ports.WorkloadInstanceResizeRequest{
			TenantID:        lifecycle.TenantID,
			InstanceID:      lifecycle.InstanceID,
			IdempotencyKey:  lifecycle.IdempotencyKey,
			Resources:       ports.WorkloadResourceRequest{CPU: firstNonEmpty(req.CPU, "4"), Memory: firstNonEmpty(req.Memory, "8Gi")},
			UserID:          lifecycle.UserID,
			PermissionProof: lifecycle.PermissionProof,
			RequestedAt:     lifecycle.RequestedAt,
		})
	case "delete":
		record, err = api.service.Delete(ctx, lifecycle)
	default:
		writeDemoError(c, http.StatusBadRequest, "BAD_REQUEST", "action must be start, stop, restart, resize, or delete")
		return
	}
	if err != nil {
		writeDemoError(c, http.StatusBadRequest, "INSTANCE_LIFECYCLE_FAILED", err.Error())
		return
	}
	c.JSON(http.StatusOK, demoInstanceFromRecord(record))
}

func (api *demoInstanceAPI) listOperations(ctx context.Context, c *app.RequestContext) {
	result, err := api.operations.ListOperations(ctx, ports.WorkloadOperationListRequest{
		TenantID:   demoTenantID(c),
		InstanceID: c.Param("instance_id"),
		Limit:      queryInt(c, "limit", 20),
		Cursor:     c.Query("cursor"),
	})
	if err != nil {
		writeDemoError(c, http.StatusBadRequest, "INSTANCE_OPERATIONS_FAILED", err.Error())
		return
	}
	items := make([]demoOperationResponse, 0, len(result.Items))
	for _, item := range result.Items {
		items = append(items, demoOperationFromRecord(item))
	}
	c.JSON(http.StatusOK, map[string]any{"items": items, "total": len(items), "next_cursor": result.NextCursor})
}

func (api *demoInstanceAPI) getOperation(ctx context.Context, c *app.RequestContext) {
	record, err := api.operations.GetOperation(ctx, demoTenantID(c), c.Param("operation_id"))
	if err != nil {
		writeDemoError(c, http.StatusNotFound, "INSTANCE_OPERATION_NOT_FOUND", err.Error())
		return
	}
	c.JSON(http.StatusOK, demoOperationFromRecord(record))
}

func (api *demoInstanceAPI) ops(ctx context.Context, c *app.RequestContext) {
	action := ports.WorkloadInstanceOpsAction(c.Param("action"))
	result, err := api.service.Ops(ctx, ports.WorkloadInstanceOpsRequest{
		TenantID:        demoTenantID(c),
		InstanceID:      c.Param("instance_id"),
		Action:          action,
		ContainerName:   "main",
		Command:         []string{"sh", "-lc", "echo ani-demo"},
		UserID:          demoUserID(c),
		PermissionProof: "demo:instance:ops",
		RequestedAt:     time.Now().UTC(),
	})
	if err != nil {
		writeDemoError(c, http.StatusBadRequest, "INSTANCE_OPS_FAILED", err.Error())
		return
	}
	c.JSON(http.StatusOK, result)
}

func (api *demoInstanceAPI) console(ctx context.Context, c *app.RequestContext) {
	var req demoConsoleRequest
	if len(c.Request.Body()) > 0 {
		if err := c.BindJSON(&req); err != nil {
			writeDemoError(c, http.StatusBadRequest, "BAD_REQUEST", "invalid console request")
			return
		}
	}
	action := consoleAction(req.Protocol)
	result, err := api.service.Ops(ctx, ports.WorkloadInstanceOpsRequest{
		TenantID:        demoTenantID(c),
		InstanceID:      c.Param("instance_id"),
		Action:          action,
		Protocol:        firstNonEmpty(req.Protocol, string(action)),
		UserID:          demoUserID(c),
		PermissionProof: "demo:instance:console",
		RequestedAt:     time.Now().UTC(),
	})
	if err != nil {
		writeDemoError(c, http.StatusBadRequest, "INSTANCE_CONSOLE_FAILED", err.Error())
		return
	}
	c.JSON(http.StatusOK, result)
}

func (api *demoInstanceAPI) consoleExec(ctx context.Context, c *app.RequestContext) {
	var req demoShellExecRequest
	if err := c.BindJSON(&req); err != nil {
		writeDemoError(c, http.StatusBadRequest, "BAD_REQUEST", "invalid shell exec request")
		return
	}
	record, err := api.service.Get(ctx, ports.WorkloadInstanceGetRequest{
		TenantID:   demoTenantID(c),
		InstanceID: c.Param("instance_id"),
	})
	if err != nil {
		writeDemoError(c, http.StatusNotFound, "INSTANCE_NOT_FOUND", err.Error())
		return
	}
	if record.Kind != ports.WorkloadKindVM {
		writeDemoError(c, http.StatusBadRequest, "INSTANCE_CONSOLE_UNSUPPORTED", "real shell console is only available for vm demo instances")
		return
	}
	if record.Status.State != ports.WorkloadStateRunning {
		writeDemoError(c, http.StatusConflict, "INSTANCE_NOT_RUNNING", "vm console requires running instance")
		return
	}
	result, err := runDemoShellCommand(ctx, record, req.Command)
	if err != nil {
		writeDemoError(c, http.StatusBadRequest, "SHELL_EXEC_FAILED", err.Error())
		return
	}
	c.JSON(http.StatusOK, result)
}

func consoleAction(protocol string) ports.WorkloadInstanceOpsAction {
	switch strings.ToLower(strings.TrimSpace(protocol)) {
	case "vnc", "novnc":
		return ports.WorkloadInstanceOpsVMVNC
	case "serial", "serial-console":
		return ports.WorkloadInstanceOpsVMSerial
	default:
		return ports.WorkloadInstanceOpsVMConsole
	}
}

func runDemoShellCommand(ctx context.Context, record ports.WorkloadInstanceRecord, command string) (demoShellExecResponse, error) {
	command = strings.TrimSpace(command)
	if command == "" {
		return demoShellExecResponse{}, fmt.Errorf("%w: command is required", ports.ErrInvalid)
	}
	if len(command) > 500 {
		return demoShellExecResponse{}, fmt.Errorf("%w: command is too long for demo shell", ports.ErrInvalid)
	}
	if blockedDemoShellCommand(command) {
		return demoShellExecResponse{}, fmt.Errorf("%w: command is blocked by demo shell guardrail", ports.ErrUnsupported)
	}
	cwd, err := demoShellCWD(record)
	if err != nil {
		return demoShellExecResponse{}, err
	}
	execCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	shell := firstNonEmpty(os.Getenv("ANI_DEMO_SHELL"), "/bin/sh")
	cmd := exec.CommandContext(execCtx, shell, "-lc", command)
	cmd.Dir = cwd
	cmd.Env = append(os.Environ(),
		"ANI_DEMO_VM_NAME="+record.Name,
		"ANI_DEMO_INSTANCE_ID="+record.InstanceID,
		"ANI_DEMO_TENANT_ID="+record.TenantID,
		"PS1=root@"+record.Name+":~# ",
	)
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	err = cmd.Run()
	exitCode := 0
	if err != nil {
		exitCode = 1
		if exitErr, ok := err.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
		}
	}
	output := strings.TrimRight(stdout.String()+stderr.String(), "\n")
	if len(output) > 16000 {
		output = output[:16000] + "\n... output truncated ..."
	}
	return demoShellExecResponse{
		Command:  command,
		Output:   output,
		ExitCode: exitCode,
		CWD:      cwd,
	}, nil
}

func demoShellCWD(record ports.WorkloadInstanceRecord) (string, error) {
	root := filepath.Join(os.TempDir(), "ani-demo-vms", sanitizePathPart(record.TenantID), sanitizePathPart(record.InstanceID))
	if err := os.MkdirAll(root, 0o700); err != nil {
		return "", err
	}
	readme := filepath.Join(root, "README.txt")
	if _, err := os.Stat(readme); os.IsNotExist(err) {
		content := "ANI demo VM shell workspace\ninstance=" + record.Name + "\nprovider=" + record.Provider + "\n"
		if writeErr := os.WriteFile(readme, []byte(content), 0o600); writeErr != nil {
			return "", writeErr
		}
	}
	return root, nil
}

func blockedDemoShellCommand(command string) bool {
	normalized := strings.ToLower(command)
	blocked := []string{
		"rm -rf /",
		"mkfs",
		"shutdown",
		"reboot",
		"halt",
		":(){",
		"dd if=",
		"chmod -r",
		"chown -r",
	}
	for _, token := range blocked {
		if strings.Contains(normalized, token) {
			return true
		}
	}
	return false
}

func sanitizePathPart(value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return "default"
	}
	replacer := strings.NewReplacer("/", "_", "\\", "_", "..", "_", ":", "_")
	return replacer.Replace(value)
}

func demoSpecFromRequest(req demoCreateInstanceRequest, tenantID string) (ports.WorkloadSpec, error) {
	kind := ports.WorkloadKind(strings.TrimSpace(req.Kind))
	if kind == "" {
		kind = ports.WorkloadKindVM
	}
	name := strings.TrimSpace(req.Name)
	if name == "" {
		name = "demo-" + string(kind)
	}
	autoStart := true
	if req.AutoStart != nil {
		autoStart = *req.AutoStart
	}
	spec := ports.WorkloadSpec{
		TenantID: tenantID,
		Name:     name,
		Kind:     kind,
		Image:    firstNonEmpty(req.Image, "registry.local/ani/demo-runtime:latest"),
		Resources: ports.WorkloadResourceRequest{
			CPU:    firstNonEmpty(req.CPU, "2"),
			Memory: firstNonEmpty(req.Memory, "4Gi"),
		},
		Network: ports.WorkloadNetworkPolicy{
			TenantIsolated: true,
			Attachments: []ports.WorkloadNetworkAttachment{
				{NetworkID: "tenant-vpc", Plane: ports.NetworkPlaneTenantVPC, Required: true, Primary: true},
				{NetworkID: "foundation-mesh", Plane: ports.NetworkPlaneFoundationMesh, Required: true},
				{NetworkID: "management", Plane: ports.NetworkPlaneManagement, Required: true},
			},
		},
		Storage: []ports.WorkloadStorageAttachment{
			{Name: name + "-root", Kind: ports.StorageAttachmentRootDisk, SizeGiB: 40, SourceRef: firstNonEmpty(req.BootImage, "images/ubuntu-22.04.qcow2"), Required: true},
		},
		Lifecycle: ports.InstanceLifecyclePolicy{AutoStart: autoStart},
		Labels: map[string]string{
			"ani.io/demo": "true",
		},
		Annotations: map[string]string{
			"ani.io/demo-description": req.Description,
		},
	}
	switch kind {
	case ports.WorkloadKindVM:
		spec.VM = &ports.VMInstanceSpec{
			BootImage:   firstNonEmpty(req.BootImage, "images/ubuntu-22.04.qcow2"),
			MachineType: "q35",
			RootDisk:    spec.Storage[0],
		}
	case ports.WorkloadKindContainer:
		spec.Storage = nil
		spec.Container = &ports.ContainerInstanceSpec{Ports: []int32{8080}}
	case ports.WorkloadKindGPUContainer:
		spec.Storage = nil
		spec.Container = &ports.ContainerInstanceSpec{Ports: []int32{8080}}
		spec.Resources.GPU = ports.GPUSchedulingRequest{
			TenantID:         tenantID,
			WorkloadID:       name,
			PreferredVendors: []ports.GPUVendor{ports.GPUVendor(firstNonEmpty(req.GPUVendor, "nvidia"))},
			PreferredModels:  []string{firstNonEmpty(req.GPUModel, "A100")},
			RequiredCount:    maxInt(req.GPUCount, 1),
		}
	default:
		return ports.WorkloadSpec{}, fmt.Errorf("unsupported demo instance kind %q", kind)
	}
	return spec, nil
}

func demoInstanceFromRecord(record ports.WorkloadInstanceRecord) demoInstanceResponse {
	return demoInstanceResponse{
		ID:           record.InstanceID,
		TenantID:     record.TenantID,
		Name:         record.Name,
		Kind:         string(record.Kind),
		Status:       string(record.Status.State),
		Provider:     record.Provider,
		OperationID:  record.OperationID,
		ResourceRefs: record.ResourceRefs,
		Endpoint:     record.Status.Endpoint,
		CreatedAt:    record.CreatedAt.Format(time.RFC3339),
		UpdatedAt:    record.UpdatedAt.Format(time.RFC3339),
	}
}

func demoManifests(manifests []ports.WorkloadManifest) []demoManifest {
	items := make([]demoManifest, 0, len(manifests))
	for _, manifest := range manifests {
		items = append(items, demoManifest{
			Name:     manifest.Name,
			Kind:     manifest.Kind,
			Provider: manifest.Provider,
			Content:  manifest.Content,
		})
	}
	return items
}

func demoTimeline(result ports.WorkloadInstanceCreateResult) []demoTimelineStep {
	return []demoTimelineStep{
		{Name: "规划", Status: "completed", Detail: "network and storage prerequisites resolved before provider rendering"},
		{Name: "渲染", Status: "completed", Detail: fmt.Sprintf("%d provider manifest rendered", len(result.Manifests))},
		{Name: "准入", Status: boolStatus(result.Admission.Allowed), Detail: result.Admission.Reason},
		{Name: "Dry-run", Status: boolStatus(result.DryRun.Accepted), Detail: result.DryRun.Reason},
		{Name: "Apply", Status: boolStatus(result.Apply.Applied), Detail: result.Apply.Reason},
		{Name: "状态回写", Status: string(result.FinalStatus.State), Detail: result.FinalStatus.Reason},
	}
}

func demoOperationFromRecord(record ports.WorkloadOperationRecord) demoOperationResponse {
	steps := make([]demoTimelineStep, 0, len(record.Steps))
	for _, step := range record.Steps {
		steps = append(steps, demoTimelineStep{
			Name:   step.StepName,
			Status: string(step.Status),
			Detail: step.Message,
		})
	}
	return demoOperationResponse{
		ID:             record.ID,
		TenantID:       record.TenantID,
		InstanceID:     record.InstanceID,
		Operation:      string(record.Operation),
		Status:         string(record.Status),
		IdempotencyKey: record.IdempotencyKey,
		RequestedBy:    record.RequestedBy,
		FailureReason:  record.FailureReason,
		FailureMessage: record.FailureMessage,
		RetryEligible:  record.RetryEligible,
		Steps:          steps,
		CreatedAt:      record.CreatedAt.Format(time.RFC3339),
		UpdatedAt:      record.UpdatedAt.Format(time.RFC3339),
	}
}

func demoTenantID(c *app.RequestContext) string {
	if tenantID := middleware.GetTenantID(c); tenantID != "" {
		return tenantID
	}
	return "demo-tenant"
}

func demoUserID(c *app.RequestContext) string {
	if value, ok := c.Get("user_id"); ok {
		if userID, ok := value.(string); ok && userID != "" {
			return userID
		}
	}
	return "demo-user"
}

func writeDemoError(c *app.RequestContext, status int, code string, message string) {
	c.JSON(status, map[string]any{
		"code":       code,
		"message":    message,
		"request_id": middleware.GetRequestID(c),
	})
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func boolStatus(ok bool) string {
	if ok {
		return "completed"
	}
	return "blocked"
}

func queryInt(c *app.RequestContext, name string, fallback int) int {
	raw := strings.TrimSpace(c.Query(name))
	if raw == "" {
		return fallback
	}
	value, err := strconv.Atoi(raw)
	if err != nil {
		return fallback
	}
	return value
}

func maxInt(value int, fallback int) int {
	if value > 0 {
		return value
	}
	return fallback
}

type demoPlanAuditStore struct{}

func (s *demoPlanAuditStore) RecordPlan(_ context.Context, _ ports.WorkloadPlanAuditRecord) (string, error) {
	return "audit_demo_" + strings.ReplaceAll(time.Now().UTC().Format("20060102150405.000000000"), ".", ""), nil
}

var _ ports.WorkloadPlanAuditStore = (*demoPlanAuditStore)(nil)

type demoGPUInventory struct{}

func (demoGPUInventory) ListNodeClasses(context.Context, ports.GPUDiscoveryFilter) ([]ports.GPUNodeClass, error) {
	return nil, nil
}

func (demoGPUInventory) GetNodeClass(context.Context, string) (ports.GPUNodeClass, error) {
	return ports.GPUNodeClass{}, ports.ErrNotFound
}

func (demoGPUInventory) PlanScheduling(_ context.Context, request ports.GPUSchedulingRequest) (ports.GPUSchedulingDecision, error) {
	quantity := fmt.Sprintf("%d", maxInt(request.RequiredCount, 1))
	return ports.GPUSchedulingDecision{
		NodeSelector:     map[string]string{"ani.io/gpu-demo": "true"},
		ResourceName:     "nvidia.com/gpu",
		ResourceQuantity: quantity,
		RuntimeClassName: "nvidia",
		SchedulerName:    "volcano",
		QueueName:        "demo-gpu",
		Reasons:          []string{"demo GPU scheduling decision"},
	}, nil
}

var _ ports.GPUInventory = demoGPUInventory{}
