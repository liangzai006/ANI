package runtime

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/kubercloud/ani/pkg/ports"
)

type MetadataMeteringService struct {
	store ports.MetadataStore
	now   func() time.Time
}

type MetadataMeteringOption func(*MetadataMeteringService)

func WithMetadataMeteringClock(now func() time.Time) MetadataMeteringOption {
	return func(service *MetadataMeteringService) {
		if now != nil {
			service.now = now
		}
	}
}

func NewMetadataMeteringService(store ports.MetadataStore, options ...MetadataMeteringOption) *MetadataMeteringService {
	service := &MetadataMeteringService{
		store: store,
		now:   time.Now,
	}
	for _, option := range options {
		option(service)
	}
	return service
}

func (s *MetadataMeteringService) QueryUsage(ctx context.Context, request ports.MeteringUsageQueryRequest) (ports.MeteringUsageResult, error) {
	if s.store == nil {
		return ports.MeteringUsageResult{}, ports.ErrNotConfigured
	}
	if strings.TrimSpace(request.TenantID) == "" {
		return ports.MeteringUsageResult{}, fmt.Errorf("%w: tenant_id is required", ports.ErrInvalid)
	}
	start := request.StartTime
	end := request.EndTime
	if end.IsZero() {
		end = s.now().UTC()
	}
	if start.IsZero() {
		start = end.Add(-24 * time.Hour)
	}

	var items []ports.MeteringUsageRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		query := `
			SELECT resource_type, COALESCE(SUM(quantity), 0)
			FROM metering_records
			WHERE tenant_id = $1::uuid
			  AND recorded_at >= $2
			  AND recorded_at <= $3
		`
		args := []any{request.TenantID, start, end}
		if request.ResourceType != "" {
			query += " AND resource_type = $4"
			args = append(args, string(request.ResourceType))
		}
		query += " GROUP BY resource_type ORDER BY resource_type"
		rows, err := tx.Query(ctx, query, args...)
		if err != nil {
			return err
		}
		defer rows.Close()
		for rows.Next() {
			var resourceType string
			var quantity float64
			if err := rows.Scan(&resourceType, &quantity); err != nil {
				return err
			}
			if quantity == 0 {
				continue
			}
			items = append(items, ports.MeteringUsageRecord{
				TenantID:      request.TenantID,
				ResourceType:  ports.MeteringResourceType(resourceType),
				TotalQuantity: quantity,
				Unit:          meteringUnitForResource(resourceType),
			})
		}
		return rows.Err()
	})
	if err != nil {
		return ports.MeteringUsageResult{}, fmt.Errorf("query metering usage: %w", err)
	}
	return ports.MeteringUsageResult{Items: items, DevProfile: meteringDevProfile()}, nil
}

func (s *MetadataMeteringService) ReportTokenUsage(ctx context.Context, request ports.TokenUsageReportRequest) (ports.TokenUsageReportRecord, error) {
	if s.store == nil {
		return ports.TokenUsageReportRecord{}, ports.ErrNotConfigured
	}
	if strings.TrimSpace(request.TenantID) == "" {
		return ports.TokenUsageReportRecord{}, fmt.Errorf("%w: tenant_id is required", ports.ErrInvalid)
	}
	if strings.TrimSpace(request.Source) == "" {
		return ports.TokenUsageReportRecord{}, fmt.Errorf("%w: source is required", ports.ErrInvalid)
	}
	if strings.TrimSpace(request.Model) == "" {
		return ports.TokenUsageReportRecord{}, fmt.Errorf("%w: model is required", ports.ErrInvalid)
	}
	if request.InputTokens < 0 || request.OutputTokens < 0 {
		return ports.TokenUsageReportRecord{}, fmt.Errorf("%w: token counts must be non-negative", ports.ErrInvalid)
	}
	idemKey, err := requireIdempotencyKey(request.TenantID, request.IdempotencyKey)
	if err != nil {
		return ports.TokenUsageReportRecord{}, err
	}
	clientKey := idempotencyClientKey(idemKey)

	var record ports.TokenUsageReportRecord
	err = s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		var existing ports.TokenUsageReportRecord
		row := tx.QueryRow(ctx, `
			SELECT id, tenant_id::text, source, model, input_tokens, output_tokens,
				COALESCE(request_id, ''), COALESCE(instance_id, ''), created_at
			FROM metering_token_reports
			WHERE tenant_id = $1::uuid AND idempotency_key = $2
		`, request.TenantID, clientKey)
		if scanErr := row.Scan(
			&existing.ReportID,
			&existing.TenantID,
			&existing.Source,
			&existing.Model,
			&existing.InputTokens,
			&existing.OutputTokens,
			&existing.RequestID,
			&existing.InstanceID,
			&existing.CreatedAt,
		); scanErr == nil {
			existing.TotalTokens = existing.InputTokens + existing.OutputTokens
			existing.State = ports.TokenUsageReportDuplicate
			existing.DevProfile = meteringDevProfile()
			record = existing
			return nil
		}

		now := firstNonZeroTime(request.OccurredAt, s.now().UTC())
		reportID := "meter_" + uuid.NewString()
		_, err := tx.Exec(ctx, `
			INSERT INTO metering_token_reports (
				id, tenant_id, idempotency_key, source, model,
				input_tokens, output_tokens, request_id, instance_id, created_at
			)
			VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, NULLIF($8, ''), NULLIF($9, ''), $10)
		`, reportID, request.TenantID, clientKey, strings.TrimSpace(request.Source), strings.TrimSpace(request.Model),
			request.InputTokens, request.OutputTokens, strings.TrimSpace(request.RequestID), strings.TrimSpace(request.InstanceID), now)
		if err != nil {
			return fmt.Errorf("insert metering token report: %w", err)
		}
		if err := insertMeteringQuantity(ctx, tx, request.TenantID, string(ports.MeteringResourceTokenInput), float64(request.InputTokens), now); err != nil {
			return err
		}
		if err := insertMeteringQuantity(ctx, tx, request.TenantID, string(ports.MeteringResourceTokenOutput), float64(request.OutputTokens), now); err != nil {
			return err
		}
		if request.InputTokens+request.OutputTokens > 0 {
			if err := insertMeteringQuantity(ctx, tx, request.TenantID, string(ports.MeteringResourceTokenTotal), float64(request.InputTokens+request.OutputTokens), now); err != nil {
				return err
			}
		}
		record = ports.TokenUsageReportRecord{
			TenantID:     request.TenantID,
			ReportID:     reportID,
			Source:       strings.TrimSpace(request.Source),
			Model:        strings.TrimSpace(request.Model),
			InputTokens:  request.InputTokens,
			OutputTokens: request.OutputTokens,
			TotalTokens:  request.InputTokens + request.OutputTokens,
			RequestID:    strings.TrimSpace(request.RequestID),
			InstanceID:   strings.TrimSpace(request.InstanceID),
			State:        ports.TokenUsageReportAccepted,
			DevProfile:   meteringDevProfile(),
			CreatedAt:    now,
		}
		return nil
	})
	if err != nil {
		return ports.TokenUsageReportRecord{}, err
	}
	return record, nil
}

func insertMeteringQuantity(ctx context.Context, tx ports.MetadataTx, tenantID string, resourceType string, quantity float64, recordedAt time.Time) error {
	if quantity <= 0 {
		return nil
	}
	_, err := tx.Exec(ctx, `
		INSERT INTO metering_records (tenant_id, az_name, resource_type, quantity, unit, recorded_at)
		VALUES ($1::uuid, 'default', $2, $3, $4, $5)
	`, tenantID, resourceType, quantity, meteringUnitForResource(resourceType), recordedAt)
	if err != nil {
		return fmt.Errorf("insert metering record: %w", err)
	}
	return nil
}

func meteringUnitForResource(resourceType string) string {
	switch resourceType {
	case string(ports.MeteringResourceTokenInput), string(ports.MeteringResourceTokenOutput), string(ports.MeteringResourceTokenTotal):
		return "token"
	default:
		return "unit"
	}
}

func idempotencyClientKey(idemKey string) string {
	if idx := strings.Index(idemKey, "\x00"); idx >= 0 && idx+1 < len(idemKey) {
		return idemKey[idx+1:]
	}
	return idemKey
}

var _ ports.MeteringService = (*MetadataMeteringService)(nil)
