package runtime

import (
	"context"
	"fmt"
	"time"

	"github.com/kubercloud/ani/pkg/ports"
)

type LocalInstanceOpsGuard struct {
	enabled bool
	now     func() time.Time
}

type InstanceOpsOption func(*LocalInstanceOpsGuard)

func WithInstanceOpsEnabled(enabled bool) InstanceOpsOption {
	return func(ops *LocalInstanceOpsGuard) {
		ops.enabled = enabled
	}
}

func WithInstanceOpsClock(now func() time.Time) InstanceOpsOption {
	return func(ops *LocalInstanceOpsGuard) {
		if now != nil {
			ops.now = now
		}
	}
}

func NewLocalInstanceOpsGuard(options ...InstanceOpsOption) *LocalInstanceOpsGuard {
	ops := &LocalInstanceOpsGuard{now: time.Now}
	for _, option := range options {
		option(ops)
	}
	return ops
}

func (g *LocalInstanceOpsGuard) Run(_ context.Context, request ports.WorkloadInstanceOpsRequest, record ports.WorkloadInstanceRecord) (ports.WorkloadInstanceOpsResult, error) {
	if err := validateOpsRequest(request, record); err != nil {
		return ports.WorkloadInstanceOpsResult{}, err
	}
	if !g.enabled {
		return ports.WorkloadInstanceOpsResult{
			Action:    request.Action,
			Accepted:  false,
			Reason:    "instance ops are disabled by execution switch",
			CheckedAt: g.now().UTC(),
		}, nil
	}
	connectURL := opsConnectURL(request, record, g.now().UTC())
	return ports.WorkloadInstanceOpsResult{
		Action:     request.Action,
		Accepted:   true,
		SessionID:  opsSessionID(request),
		Protocol:   opsProtocol(request),
		ConnectURL: connectURL,
		URL:        connectURL,
		Reason:     "accepted by local instance ops guard",
		CheckedAt:  g.now().UTC(),
		ExpiresAt:  g.now().UTC().Add(15 * time.Minute),
	}, nil
}

func validateOpsRequest(request ports.WorkloadInstanceOpsRequest, record ports.WorkloadInstanceRecord) error {
	if request.TenantID == "" || request.InstanceID == "" {
		return fmt.Errorf("%w: tenantID and instanceID are required for instance ops", ports.ErrInvalid)
	}
	if request.UserID == "" || request.PermissionProof == "" {
		return fmt.Errorf("%w: user id and permission proof are required for instance ops", ports.ErrInvalid)
	}
	if request.TenantID != record.TenantID || request.InstanceID != record.InstanceID {
		return fmt.Errorf("%w: ops request does not match instance record", ports.ErrInvalid)
	}
	switch request.Action {
	case ports.WorkloadInstanceOpsLogs, ports.WorkloadInstanceOpsEvents, ports.WorkloadInstanceOpsMetrics:
		return nil
	case ports.WorkloadInstanceOpsTerminal, ports.WorkloadInstanceOpsExec:
		if record.Kind == ports.WorkloadKindVM {
			return fmt.Errorf("%w: terminal and exec ops are container-only", ports.ErrUnsupported)
		}
		if record.Status.State != ports.WorkloadStateRunning {
			return fmt.Errorf("%w: terminal and exec require running instance", ports.ErrConflict)
		}
		return nil
	case ports.WorkloadInstanceOpsVMConsole, ports.WorkloadInstanceOpsVMVNC, ports.WorkloadInstanceOpsVMSerial:
		if record.Kind != ports.WorkloadKindVM {
			return fmt.Errorf("%w: vm console ops require vm instance", ports.ErrUnsupported)
		}
		if record.Status.State != ports.WorkloadStateRunning {
			return fmt.Errorf("%w: vm console ops require running instance", ports.ErrConflict)
		}
		return nil
	default:
		return fmt.Errorf("%w: unsupported instance ops action %q", ports.ErrUnsupported, request.Action)
	}
}

func opsSessionID(request ports.WorkloadInstanceOpsRequest) string {
	switch request.Action {
	case ports.WorkloadInstanceOpsTerminal, ports.WorkloadInstanceOpsExec,
		ports.WorkloadInstanceOpsVMConsole, ports.WorkloadInstanceOpsVMVNC, ports.WorkloadInstanceOpsVMSerial:
		return request.InstanceID + "/" + string(request.Action)
	default:
		return ""
	}
}

func opsProtocol(request ports.WorkloadInstanceOpsRequest) string {
	if request.Protocol != "" {
		return request.Protocol
	}
	switch request.Action {
	case ports.WorkloadInstanceOpsVMVNC:
		return "vnc"
	case ports.WorkloadInstanceOpsVMSerial:
		return "serial-console"
	case ports.WorkloadInstanceOpsVMConsole:
		return "console"
	case ports.WorkloadInstanceOpsTerminal:
		return "web-terminal"
	case ports.WorkloadInstanceOpsExec:
		return "exec"
	default:
		return ""
	}
}

func opsConnectURL(request ports.WorkloadInstanceOpsRequest, record ports.WorkloadInstanceRecord, checkedAt time.Time) string {
	protocol := opsProtocol(request)
	if protocol == "" {
		return ""
	}
	return "/api/v1/demo/instances/" + record.InstanceID + "/sessions/" + string(request.Action) + "?protocol=" + protocol + "&issued_at=" + checkedAt.Format("20060102150405")
}

var _ ports.WorkloadInstanceOps = (*LocalInstanceOpsGuard)(nil)
