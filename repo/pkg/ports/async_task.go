package ports

import (
	"context"
	"encoding/json"
	"time"
)

type AsyncTaskRecord struct {
	ID              string
	TenantID        string
	IdempotencyKey  string
	TaskType        string
	ResourceType    string
	ResourceID      string
	Status          string
	AttemptCount    int
	MaxAttempts     int
	ProgressPct     int
	Result          json.RawMessage
	ErrorMessage    string
	DeadLetterAt    *time.Time
	CreatedAt       time.Time
	StartedAt       *time.Time
	CompletedAt     *time.Time
}

type AsyncTaskService interface {
	GetTask(ctx context.Context, tenantID string, taskID string) (AsyncTaskRecord, error)
	CancelTask(ctx context.Context, tenantID string, taskID string) (AsyncTaskRecord, error)
}
