package runtime

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/kubercloud/ani/pkg/ports"
)

type MetadataRegistryStore struct {
	store ports.MetadataStore
	now   func() time.Time
}

type RegistryStoreOption func(*MetadataRegistryStore)

func WithRegistryStoreClock(now func() time.Time) RegistryStoreOption {
	return func(store *MetadataRegistryStore) {
		if now != nil {
			store.now = now
		}
	}
}

func NewMetadataRegistryStore(store ports.MetadataStore, options ...RegistryStoreOption) *MetadataRegistryStore {
	registryStore := &MetadataRegistryStore{
		store: store,
		now:   time.Now,
	}
	for _, option := range options {
		option(registryStore)
	}
	return registryStore
}

func (s *MetadataRegistryStore) UpsertProject(ctx context.Context, record ports.RegistryProjectRecord, idempotencyKey string) error {
	if s.store == nil {
		return ports.ErrNotConfigured
	}
	if err := requireRegistryTenant(record.TenantID); err != nil {
		return err
	}
	projectID := strings.TrimSpace(record.ProjectID)
	name := strings.TrimSpace(record.Name)
	if projectID == "" || name == "" {
		return fmt.Errorf("%w: registry project id and name are required", ports.ErrInvalid)
	}
	providerMode := strings.TrimSpace(record.ProviderMode)
	if providerMode == "" {
		providerMode = "local"
	}
	createdAt, updatedAt := networkRecordTimes(s.now, record.CreatedAt, record.UpdatedAt)
	idemKey := strings.TrimSpace(idempotencyKey)
	return s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		_, err := tx.Exec(ctx, `
			INSERT INTO registry_projects (tenant_id, project_id, name, public, provider_mode, idempotency_key, created_at, updated_at)
			VALUES ($1::uuid, $2, $3, $4, $5, NULLIF($6, ''), $7, $8)
			ON CONFLICT (tenant_id, name) DO UPDATE SET
				project_id = EXCLUDED.project_id,
				public = EXCLUDED.public,
				provider_mode = EXCLUDED.provider_mode,
				idempotency_key = COALESCE(NULLIF(EXCLUDED.idempotency_key, ''), registry_projects.idempotency_key),
				updated_at = EXCLUDED.updated_at
		`, record.TenantID, projectID, name, record.Public, providerMode, idemKey, createdAt, updatedAt)
		if err != nil {
			return fmt.Errorf("upsert registry project: %w", err)
		}
		return nil
	})
}

func (s *MetadataRegistryStore) ListProjects(ctx context.Context, tenantID string) ([]ports.RegistryProjectRecord, error) {
	if s.store == nil {
		return nil, ports.ErrNotConfigured
	}
	if err := requireRegistryTenant(tenantID); err != nil {
		return nil, err
	}
	var records []ports.RegistryProjectRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		rows, err := tx.Query(ctx, `
			SELECT project_id, name, public, provider_mode, created_at, updated_at
			FROM registry_projects
			WHERE tenant_id = $1::uuid
			ORDER BY created_at ASC
		`, tenantID)
		if err != nil {
			return fmt.Errorf("list registry projects: %w", err)
		}
		defer rows.Close()
		for rows.Next() {
			var record ports.RegistryProjectRecord
			record.TenantID = tenantID
			if err := rows.Scan(&record.ProjectID, &record.Name, &record.Public, &record.ProviderMode, &record.CreatedAt, &record.UpdatedAt); err != nil {
				return fmt.Errorf("scan registry project: %w", err)
			}
			records = append(records, record)
		}
		return rows.Err()
	})
	return records, err
}

func (s *MetadataRegistryStore) GetProjectByIdempotency(ctx context.Context, tenantID, idempotencyKey string) (ports.RegistryProjectRecord, error) {
	if s.store == nil {
		return ports.RegistryProjectRecord{}, ports.ErrNotConfigured
	}
	if err := requireRegistryTenant(tenantID); err != nil {
		return ports.RegistryProjectRecord{}, err
	}
	idemKey := strings.TrimSpace(idempotencyKey)
	if idemKey == "" {
		return ports.RegistryProjectRecord{}, fmt.Errorf("%w: idempotency_key is required", ports.ErrInvalid)
	}
	var record ports.RegistryProjectRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		row := tx.QueryRow(ctx, `
			SELECT project_id, name, public, provider_mode, created_at, updated_at
			FROM registry_projects
			WHERE tenant_id = $1::uuid AND idempotency_key = $2
		`, tenantID, idemKey)
		record.TenantID = tenantID
		if err := row.Scan(&record.ProjectID, &record.Name, &record.Public, &record.ProviderMode, &record.CreatedAt, &record.UpdatedAt); err != nil {
			if errors.Is(err, pgx.ErrNoRows) {
				return ports.ErrNotFound
			}
			return fmt.Errorf("get registry project by idempotency: %w", err)
		}
		return nil
	})
	return record, err
}

func (s *MetadataRegistryStore) UpsertRepositoryPermission(ctx context.Context, record ports.RegistryPermissionRecord, idempotencyKey string) error {
	if s.store == nil {
		return ports.ErrNotConfigured
	}
	if err := requireRegistryTenant(record.TenantID); err != nil {
		return err
	}
	project := strings.TrimSpace(record.Project)
	repository := strings.TrimSpace(record.Repository)
	subject := strings.TrimSpace(record.Subject)
	if project == "" || repository == "" || subject == "" {
		return fmt.Errorf("%w: registry permission project, repository and subject are required", ports.ErrInvalid)
	}
	if len(record.Actions) == 0 {
		return fmt.Errorf("%w: registry permission actions are required", ports.ErrInvalid)
	}
	actionsJSON, err := json.Marshal(registryActionsToStrings(record.Actions))
	if err != nil {
		return fmt.Errorf("marshal registry permission actions: %w", err)
	}
	state := string(record.State)
	if state == "" {
		state = string(ports.RegistryPermissionActive)
	}
	updatedAt := record.UpdatedAt
	if updatedAt.IsZero() {
		updatedAt = s.now().UTC()
	}
	idemKey := strings.TrimSpace(idempotencyKey)
	return s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		_, err := tx.Exec(ctx, `
			INSERT INTO registry_repository_permissions (tenant_id, project, repository, subject, actions, state, idempotency_key, updated_at)
			VALUES ($1::uuid, $2, $3, $4, $5::jsonb, $6, NULLIF($7, ''), $8)
			ON CONFLICT (tenant_id, project, repository, subject) DO UPDATE SET
				actions = EXCLUDED.actions,
				state = EXCLUDED.state,
				idempotency_key = COALESCE(NULLIF(EXCLUDED.idempotency_key, ''), registry_repository_permissions.idempotency_key),
				updated_at = EXCLUDED.updated_at
		`, record.TenantID, project, repository, subject, actionsJSON, state, idemKey, updatedAt)
		if err != nil {
			return fmt.Errorf("upsert registry repository permission: %w", err)
		}
		return nil
	})
}

func (s *MetadataRegistryStore) GetPermissionByIdempotency(ctx context.Context, tenantID, idempotencyKey string) (ports.RegistryPermissionRecord, error) {
	if s.store == nil {
		return ports.RegistryPermissionRecord{}, ports.ErrNotConfigured
	}
	if err := requireRegistryTenant(tenantID); err != nil {
		return ports.RegistryPermissionRecord{}, err
	}
	idemKey := strings.TrimSpace(idempotencyKey)
	if idemKey == "" {
		return ports.RegistryPermissionRecord{}, fmt.Errorf("%w: idempotency_key is required", ports.ErrInvalid)
	}
	var record ports.RegistryPermissionRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		var actionsJSON []byte
		var state string
		row := tx.QueryRow(ctx, `
			SELECT project, repository, subject, actions, state, updated_at
			FROM registry_repository_permissions
			WHERE tenant_id = $1::uuid AND idempotency_key = $2
		`, tenantID, idemKey)
		record.TenantID = tenantID
		if err := row.Scan(&record.Project, &record.Repository, &record.Subject, &actionsJSON, &state, &record.UpdatedAt); err != nil {
			if errors.Is(err, pgx.ErrNoRows) {
				return ports.ErrNotFound
			}
			return fmt.Errorf("get registry permission by idempotency: %w", err)
		}
		actions, err := parseRegistryActionsJSON(actionsJSON)
		if err != nil {
			return err
		}
		record.Actions = actions
		record.State = ports.RegistryPermissionState(state)
		return nil
	})
	return record, err
}

func (s *MetadataRegistryStore) GetRepositoryPermission(ctx context.Context, tenantID, project, repository, subject string) (ports.RegistryPermissionRecord, error) {
	if s.store == nil {
		return ports.RegistryPermissionRecord{}, ports.ErrNotConfigured
	}
	if err := requireRegistryTenant(tenantID); err != nil {
		return ports.RegistryPermissionRecord{}, err
	}
	project = strings.TrimSpace(project)
	repository = strings.TrimSpace(repository)
	subject = strings.TrimSpace(subject)
	if project == "" || repository == "" || subject == "" {
		return ports.RegistryPermissionRecord{}, fmt.Errorf("%w: registry permission project, repository and subject are required", ports.ErrInvalid)
	}
	var record ports.RegistryPermissionRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		var actionsJSON []byte
		var state string
		row := tx.QueryRow(ctx, `
			SELECT project, repository, subject, actions, state, updated_at
			FROM registry_repository_permissions
			WHERE tenant_id = $1::uuid AND project = $2 AND repository = $3 AND subject = $4
		`, tenantID, project, repository, subject)
		record.TenantID = tenantID
		if err := row.Scan(&record.Project, &record.Repository, &record.Subject, &actionsJSON, &state, &record.UpdatedAt); err != nil {
			if errors.Is(err, pgx.ErrNoRows) {
				return ports.ErrNotFound
			}
			return fmt.Errorf("get registry repository permission: %w", err)
		}
		actions, err := parseRegistryActionsJSON(actionsJSON)
		if err != nil {
			return err
		}
		record.Actions = actions
		record.State = ports.RegistryPermissionState(state)
		return nil
	})
	return record, err
}

func (s *MetadataRegistryStore) UpsertPullSecret(ctx context.Context, record ports.RegistryPullSecretRecord, idempotencyKey string) error {
	if s.store == nil {
		return ports.ErrNotConfigured
	}
	if err := requireRegistryTenant(record.TenantID); err != nil {
		return err
	}
	project := strings.TrimSpace(record.Project)
	name := strings.TrimSpace(record.Name)
	if project == "" || name == "" {
		return fmt.Errorf("%w: registry pull secret project and name are required", ports.ErrInvalid)
	}
	state := string(record.State)
	if state == "" {
		state = string(ports.RegistryPermissionActive)
	}
	createdAt, updatedAt := networkRecordTimes(s.now, record.CreatedAt, record.UpdatedAt)
	idemKey := strings.TrimSpace(idempotencyKey)
	return s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		_, err := tx.Exec(ctx, `
			INSERT INTO registry_pull_secrets (tenant_id, project, name, secret_ref, registry_host, username, namespace, state, idempotency_key, created_at, updated_at)
			VALUES ($1::uuid, $2, $3, $4, $5, $6, NULLIF($7, ''), $8, NULLIF($9, ''), $10, $11)
			ON CONFLICT (tenant_id, project, name) DO UPDATE SET
				secret_ref = EXCLUDED.secret_ref,
				registry_host = EXCLUDED.registry_host,
				username = EXCLUDED.username,
				namespace = EXCLUDED.namespace,
				state = EXCLUDED.state,
				idempotency_key = COALESCE(NULLIF(EXCLUDED.idempotency_key, ''), registry_pull_secrets.idempotency_key),
				updated_at = EXCLUDED.updated_at
		`, record.TenantID, project, name, record.SecretRef, record.Registry, record.Username, record.Namespace, state, idemKey, createdAt, updatedAt)
		if err != nil {
			return fmt.Errorf("upsert registry pull secret: %w", err)
		}
		return nil
	})
}

func (s *MetadataRegistryStore) GetPullSecretByIdempotency(ctx context.Context, tenantID, idempotencyKey string) (ports.RegistryPullSecretRecord, error) {
	if s.store == nil {
		return ports.RegistryPullSecretRecord{}, ports.ErrNotConfigured
	}
	if err := requireRegistryTenant(tenantID); err != nil {
		return ports.RegistryPullSecretRecord{}, err
	}
	idemKey := strings.TrimSpace(idempotencyKey)
	if idemKey == "" {
		return ports.RegistryPullSecretRecord{}, fmt.Errorf("%w: idempotency_key is required", ports.ErrInvalid)
	}
	var record ports.RegistryPullSecretRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		var namespace *string
		var state string
		row := tx.QueryRow(ctx, `
			SELECT project, name, secret_ref, registry_host, username, namespace, state, created_at, updated_at
			FROM registry_pull_secrets
			WHERE tenant_id = $1::uuid AND idempotency_key = $2
		`, tenantID, idemKey)
		record.TenantID = tenantID
		if err := row.Scan(&record.Project, &record.Name, &record.SecretRef, &record.Registry, &record.Username, &namespace, &state, &record.CreatedAt, &record.UpdatedAt); err != nil {
			if errors.Is(err, pgx.ErrNoRows) {
				return ports.ErrNotFound
			}
			return fmt.Errorf("get registry pull secret by idempotency: %w", err)
		}
		if namespace != nil {
			record.Namespace = *namespace
		}
		record.State = ports.RegistryPermissionState(state)
		return nil
	})
	return record, err
}

func requireRegistryTenant(tenantID string) error {
	if strings.TrimSpace(tenantID) == "" {
		return fmt.Errorf("%w: tenant_id is required", ports.ErrInvalid)
	}
	return nil
}

func registryActionsToStrings(actions []ports.RegistryPermissionAction) []string {
	out := make([]string, 0, len(actions))
	for _, action := range actions {
		out = append(out, string(action))
	}
	return out
}

func parseRegistryActionsJSON(payload []byte) ([]ports.RegistryPermissionAction, error) {
	var raw []string
	if err := json.Unmarshal(payload, &raw); err != nil {
		return nil, fmt.Errorf("parse registry permission actions: %w", err)
	}
	actions := make([]ports.RegistryPermissionAction, 0, len(raw))
	for _, action := range raw {
		actions = append(actions, ports.RegistryPermissionAction(action))
	}
	return actions, nil
}

var _ ports.RegistryResourceStore = (*MetadataRegistryStore)(nil)
