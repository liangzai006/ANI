package runtime

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/kubercloud/ani/pkg/ports"
)

type MetadataAsyncTaskService struct {
	store ports.MetadataStore
}

func NewMetadataAsyncTaskService(store ports.MetadataStore) *MetadataAsyncTaskService {
	return &MetadataAsyncTaskService{store: store}
}

func (s *MetadataAsyncTaskService) GetTask(ctx context.Context, tenantID string, taskID string) (ports.AsyncTaskRecord, error) {
	if s.store == nil {
		return ports.AsyncTaskRecord{}, ports.ErrNotConfigured
	}
	if err := requireAsyncTaskIDs(tenantID, taskID); err != nil {
		return ports.AsyncTaskRecord{}, err
	}
	var record ports.AsyncTaskRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		row := tx.QueryRow(ctx, `
			SELECT id::text, tenant_id::text, idempotency_key, task_type,
				COALESCE(resource_type, ''),
				COALESCE(resource_id::text, ''),
				status, attempt_count, max_attempts, progress_pct,
				result, COALESCE(error_message, ''),
				dead_letter_at, created_at, started_at, completed_at
			FROM async_tasks
			WHERE tenant_id = $1::uuid AND id = $2::uuid
		`, tenantID, taskID)
		return scanAsyncTask(row, &record)
	})
	if err != nil {
		return ports.AsyncTaskRecord{}, err
	}
	return record, nil
}

func (s *MetadataAsyncTaskService) CancelTask(ctx context.Context, tenantID string, taskID string) (ports.AsyncTaskRecord, error) {
	if s.store == nil {
		return ports.AsyncTaskRecord{}, ports.ErrNotConfigured
	}
	if err := requireAsyncTaskIDs(tenantID, taskID); err != nil {
		return ports.AsyncTaskRecord{}, err
	}
	var record ports.AsyncTaskRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		row := tx.QueryRow(ctx, `
			UPDATE async_tasks
			SET status = 'cancelled',
				updated_at = NOW(),
				completed_at = COALESCE(completed_at, NOW())
			WHERE tenant_id = $1::uuid
			  AND id = $2::uuid
			  AND status IN ('pending', 'running', 'failed')
			RETURNING id::text, tenant_id::text, idempotency_key, task_type,
				COALESCE(resource_type, ''),
				COALESCE(resource_id::text, ''),
				status, attempt_count, max_attempts, progress_pct,
				result, COALESCE(error_message, ''),
				dead_letter_at, created_at, started_at, completed_at
		`, tenantID, taskID)
		if err := scanAsyncTask(row, &record); err != nil {
			return err
		}
		return nil
	})
	if err != nil {
		return ports.AsyncTaskRecord{}, err
	}
	return record, nil
}

func requireAsyncTaskIDs(tenantID, taskID string) error {
	if strings.TrimSpace(tenantID) == "" {
		return fmt.Errorf("%w: tenant_id is required", ports.ErrInvalid)
	}
	if _, err := uuid.Parse(strings.TrimSpace(taskID)); err != nil {
		return fmt.Errorf("%w: invalid task_id", ports.ErrInvalid)
	}
	return nil
}

func scanAsyncTask(row ports.Row, record *ports.AsyncTaskRecord) error {
	var result []byte
	var deadLetterAt *time.Time
	var startedAt *time.Time
	var completedAt *time.Time
	if err := row.Scan(
		&record.ID,
		&record.TenantID,
		&record.IdempotencyKey,
		&record.TaskType,
		&record.ResourceType,
		&record.ResourceID,
		&record.Status,
		&record.AttemptCount,
		&record.MaxAttempts,
		&record.ProgressPct,
		&result,
		&record.ErrorMessage,
		&deadLetterAt,
		&record.CreatedAt,
		&startedAt,
		&completedAt,
	); err != nil {
		return ports.ErrNotFound
	}
	if len(result) > 0 {
		record.Result = json.RawMessage(result)
	}
	record.DeadLetterAt = deadLetterAt
	record.StartedAt = startedAt
	record.CompletedAt = completedAt
	return nil
}

var _ ports.AsyncTaskService = (*MetadataAsyncTaskService)(nil)

type LocalAsyncTaskService struct{}

func NewLocalAsyncTaskService() *LocalAsyncTaskService {
	return &LocalAsyncTaskService{}
}

func (s *LocalAsyncTaskService) GetTask(context.Context, string, string) (ports.AsyncTaskRecord, error) {
	return ports.AsyncTaskRecord{}, ports.ErrNotFound
}

func (s *LocalAsyncTaskService) CancelTask(context.Context, string, string) (ports.AsyncTaskRecord, error) {
	return ports.AsyncTaskRecord{}, ports.ErrNotFound
}

var _ ports.AsyncTaskService = (*LocalAsyncTaskService)(nil)
