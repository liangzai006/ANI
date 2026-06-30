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

type MetadataK8sClusterStore struct {
	store ports.MetadataStore
	now   func() time.Time
}

type K8sClusterStoreOption func(*MetadataK8sClusterStore)

func WithK8sClusterStoreClock(now func() time.Time) K8sClusterStoreOption {
	return func(store *MetadataK8sClusterStore) {
		if now != nil {
			store.now = now
		}
	}
}

func NewMetadataK8sClusterStore(store ports.MetadataStore, options ...K8sClusterStoreOption) *MetadataK8sClusterStore {
	clusterStore := &MetadataK8sClusterStore{
		store: store,
		now:   time.Now,
	}
	for _, option := range options {
		option(clusterStore)
	}
	return clusterStore
}

func (s *MetadataK8sClusterStore) UpsertCluster(ctx context.Context, record ports.K8sClusterRecord, idempotencyKey string) error {
	if s.store == nil {
		return ports.ErrNotConfigured
	}
	if err := requireK8sClusterTenant(record.TenantID); err != nil {
		return err
	}
	clusterID := strings.TrimSpace(record.ClusterID)
	name := strings.TrimSpace(record.Name)
	if clusterID == "" || name == "" {
		return fmt.Errorf("%w: k8s cluster id and name are required", ports.ErrInvalid)
	}
	provider := strings.TrimSpace(record.Provider)
	if provider == "" {
		provider = "local"
	}
	state := string(record.State)
	if state == "" {
		state = string(ports.K8sClusterStateRunning)
	}
	refsJSON, err := json.Marshal(record.ProviderRefs)
	if err != nil {
		return fmt.Errorf("marshal k8s cluster provider refs: %w", err)
	}
	createdAt, updatedAt := k8sClusterUnixTimes(s.now, record.CreatedAt, record.UpdatedAt)
	idemKey := strings.TrimSpace(idempotencyKey)
	return s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		_, err := tx.Exec(ctx, `
			INSERT INTO k8s_clusters (
				tenant_id, cluster_id, name, version, state, reason, provider, real_provider, provider_refs,
				idempotency_key, created_at, updated_at
			)
			VALUES ($1::uuid, $2, $3, $4, $5, NULLIF($6, ''), $7, $8, $9::jsonb, NULLIF($10, ''), $11, $12)
			ON CONFLICT (tenant_id, cluster_id) DO UPDATE SET
				name = EXCLUDED.name,
				version = EXCLUDED.version,
				state = EXCLUDED.state,
				reason = EXCLUDED.reason,
				provider = EXCLUDED.provider,
				real_provider = EXCLUDED.real_provider,
				provider_refs = EXCLUDED.provider_refs,
				idempotency_key = COALESCE(NULLIF(EXCLUDED.idempotency_key, ''), k8s_clusters.idempotency_key),
				updated_at = EXCLUDED.updated_at
		`, record.TenantID, clusterID, name, record.Version, state, record.Reason, provider, record.RealProvider, string(refsJSON), idemKey, createdAt, updatedAt)
		if err != nil {
			return fmt.Errorf("upsert k8s cluster: %w", err)
		}
		return nil
	})
}

func (s *MetadataK8sClusterStore) GetCluster(ctx context.Context, tenantID, clusterID string) (ports.K8sClusterRecord, error) {
	if s.store == nil {
		return ports.K8sClusterRecord{}, ports.ErrNotConfigured
	}
	if err := requireK8sClusterTenant(tenantID); err != nil {
		return ports.K8sClusterRecord{}, err
	}
	clusterID = strings.TrimSpace(clusterID)
	if clusterID == "" {
		return ports.K8sClusterRecord{}, fmt.Errorf("%w: cluster_id is required", ports.ErrInvalid)
	}
	var record ports.K8sClusterRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		return scanK8sClusterRow(tx.QueryRow(ctx, `
			SELECT cluster_id, name, version, state, reason, provider, real_provider, provider_refs, created_at, updated_at
			FROM k8s_clusters
			WHERE tenant_id = $1::uuid AND cluster_id = $2
		`, tenantID, clusterID), tenantID, &record)
	})
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return ports.K8sClusterRecord{}, ports.ErrNotFound
		}
		return ports.K8sClusterRecord{}, err
	}
	return record, nil
}

func (s *MetadataK8sClusterStore) ListClusters(ctx context.Context, tenantID string) ([]ports.K8sClusterRecord, error) {
	if s.store == nil {
		return nil, ports.ErrNotConfigured
	}
	if err := requireK8sClusterTenant(tenantID); err != nil {
		return nil, err
	}
	var records []ports.K8sClusterRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		rows, err := tx.Query(ctx, `
			SELECT cluster_id, name, version, state, reason, provider, real_provider, provider_refs, created_at, updated_at
			FROM k8s_clusters
			WHERE tenant_id = $1::uuid
			ORDER BY created_at ASC
		`, tenantID)
		if err != nil {
			return fmt.Errorf("list k8s clusters: %w", err)
		}
		defer rows.Close()
		for rows.Next() {
			var record ports.K8sClusterRecord
			if err := scanK8sClusterRows(rows, tenantID, &record); err != nil {
				return err
			}
			records = append(records, record)
		}
		return rows.Err()
	})
	return records, err
}

func (s *MetadataK8sClusterStore) GetClusterByIdempotency(ctx context.Context, tenantID, idempotencyKey string) (ports.K8sClusterRecord, error) {
	if s.store == nil {
		return ports.K8sClusterRecord{}, ports.ErrNotConfigured
	}
	if err := requireK8sClusterTenant(tenantID); err != nil {
		return ports.K8sClusterRecord{}, err
	}
	idemKey := strings.TrimSpace(idempotencyKey)
	if idemKey == "" {
		return ports.K8sClusterRecord{}, fmt.Errorf("%w: idempotency_key is required", ports.ErrInvalid)
	}
	var record ports.K8sClusterRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		return scanK8sClusterRow(tx.QueryRow(ctx, `
			SELECT cluster_id, name, version, state, reason, provider, real_provider, provider_refs, created_at, updated_at
			FROM k8s_clusters
			WHERE tenant_id = $1::uuid AND idempotency_key = $2
		`, tenantID, idemKey), tenantID, &record)
	})
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return ports.K8sClusterRecord{}, ports.ErrNotFound
		}
		return ports.K8sClusterRecord{}, err
	}
	return record, nil
}

func (s *MetadataK8sClusterStore) UpsertNodePool(ctx context.Context, record ports.K8sClusterNodePoolRecord, idempotencyKey string) error {
	if s.store == nil {
		return ports.ErrNotConfigured
	}
	if err := requireK8sClusterTenant(record.TenantID); err != nil {
		return err
	}
	nodePoolID := strings.TrimSpace(record.NodePoolID)
	clusterID := strings.TrimSpace(record.ClusterID)
	name := strings.TrimSpace(record.Name)
	instanceType := strings.TrimSpace(record.InstanceType)
	if nodePoolID == "" || clusterID == "" || name == "" || instanceType == "" {
		return fmt.Errorf("%w: k8s node pool id, cluster id, name and instance_type are required", ports.ErrInvalid)
	}
	provider := strings.TrimSpace(record.Provider)
	if provider == "" {
		provider = "local"
	}
	state := string(record.State)
	if state == "" {
		state = string(ports.K8sClusterNodePoolStateRunning)
	}
	refsJSON, err := json.Marshal(record.ProviderRefs)
	if err != nil {
		return fmt.Errorf("marshal k8s node pool provider refs: %w", err)
	}
	createdAt, updatedAt := k8sClusterUnixTimes(s.now, record.CreatedAt, record.UpdatedAt)
	idemKey := strings.TrimSpace(idempotencyKey)
	return s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		_, err := tx.Exec(ctx, `
			INSERT INTO k8s_cluster_node_pools (
				tenant_id, cluster_id, node_pool_id, name, node_count, instance_type,
				gpu_vendor, gpu_model, gpu_count, gpu_resource_name,
				state, reason, provider, real_provider, provider_refs,
				idempotency_key, created_at, updated_at
			)
			VALUES (
				$1::uuid, $2, $3, $4, $5, $6,
				NULLIF($7, ''), NULLIF($8, ''), $9, NULLIF($10, ''),
				$11, NULLIF($12, ''), $13, $14, $15::jsonb,
				NULLIF($16, ''), $17, $18
			)
			ON CONFLICT (tenant_id, node_pool_id) DO UPDATE SET
				cluster_id = EXCLUDED.cluster_id,
				name = EXCLUDED.name,
				node_count = EXCLUDED.node_count,
				instance_type = EXCLUDED.instance_type,
				gpu_vendor = EXCLUDED.gpu_vendor,
				gpu_model = EXCLUDED.gpu_model,
				gpu_count = EXCLUDED.gpu_count,
				gpu_resource_name = EXCLUDED.gpu_resource_name,
				state = EXCLUDED.state,
				reason = EXCLUDED.reason,
				provider = EXCLUDED.provider,
				real_provider = EXCLUDED.real_provider,
				provider_refs = EXCLUDED.provider_refs,
				idempotency_key = COALESCE(NULLIF(EXCLUDED.idempotency_key, ''), k8s_cluster_node_pools.idempotency_key),
				updated_at = EXCLUDED.updated_at
		`,
			record.TenantID, clusterID, nodePoolID, name, record.NodeCount, instanceType,
			record.GPU.Vendor, record.GPU.Model, record.GPU.Count, record.GPU.ResourceName,
			state, record.Reason, provider, record.RealProvider, string(refsJSON),
			idemKey, createdAt, updatedAt,
		)
		if err != nil {
			return fmt.Errorf("upsert k8s cluster node pool: %w", err)
		}
		return nil
	})
}

func (s *MetadataK8sClusterStore) GetNodePool(ctx context.Context, tenantID, clusterID, nodePoolID string) (ports.K8sClusterNodePoolRecord, error) {
	if s.store == nil {
		return ports.K8sClusterNodePoolRecord{}, ports.ErrNotConfigured
	}
	if err := requireK8sClusterTenant(tenantID); err != nil {
		return ports.K8sClusterNodePoolRecord{}, err
	}
	clusterID = strings.TrimSpace(clusterID)
	nodePoolID = strings.TrimSpace(nodePoolID)
	if clusterID == "" || nodePoolID == "" {
		return ports.K8sClusterNodePoolRecord{}, fmt.Errorf("%w: cluster_id and node_pool_id are required", ports.ErrInvalid)
	}
	var record ports.K8sClusterNodePoolRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		return scanK8sNodePoolRow(tx.QueryRow(ctx, `
			SELECT cluster_id, node_pool_id, name, node_count, instance_type,
				gpu_vendor, gpu_model, gpu_count, gpu_resource_name,
				state, reason, provider, real_provider, provider_refs, created_at, updated_at
			FROM k8s_cluster_node_pools
			WHERE tenant_id = $1::uuid AND cluster_id = $2 AND node_pool_id = $3
		`, tenantID, clusterID, nodePoolID), tenantID, &record)
	})
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return ports.K8sClusterNodePoolRecord{}, ports.ErrNotFound
		}
		return ports.K8sClusterNodePoolRecord{}, err
	}
	return record, nil
}

func (s *MetadataK8sClusterStore) ListNodePools(ctx context.Context, tenantID, clusterID string) ([]ports.K8sClusterNodePoolRecord, error) {
	if s.store == nil {
		return nil, ports.ErrNotConfigured
	}
	if err := requireK8sClusterTenant(tenantID); err != nil {
		return nil, err
	}
	clusterID = strings.TrimSpace(clusterID)
	if clusterID == "" {
		return nil, fmt.Errorf("%w: cluster_id is required", ports.ErrInvalid)
	}
	var records []ports.K8sClusterNodePoolRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		rows, err := tx.Query(ctx, `
			SELECT cluster_id, node_pool_id, name, node_count, instance_type,
				gpu_vendor, gpu_model, gpu_count, gpu_resource_name,
				state, reason, provider, real_provider, provider_refs, created_at, updated_at
			FROM k8s_cluster_node_pools
			WHERE tenant_id = $1::uuid AND cluster_id = $2
			ORDER BY created_at ASC
		`, tenantID, clusterID)
		if err != nil {
			return fmt.Errorf("list k8s cluster node pools: %w", err)
		}
		defer rows.Close()
		for rows.Next() {
			var record ports.K8sClusterNodePoolRecord
			if err := scanK8sNodePoolRows(rows, tenantID, &record); err != nil {
				return err
			}
			records = append(records, record)
		}
		return rows.Err()
	})
	return records, err
}

func (s *MetadataK8sClusterStore) GetNodePoolByIdempotency(ctx context.Context, tenantID, clusterID, idempotencyKey string) (ports.K8sClusterNodePoolRecord, error) {
	if s.store == nil {
		return ports.K8sClusterNodePoolRecord{}, ports.ErrNotConfigured
	}
	if err := requireK8sClusterTenant(tenantID); err != nil {
		return ports.K8sClusterNodePoolRecord{}, err
	}
	clusterID = strings.TrimSpace(clusterID)
	idemKey := strings.TrimSpace(idempotencyKey)
	if clusterID == "" || idemKey == "" {
		return ports.K8sClusterNodePoolRecord{}, fmt.Errorf("%w: cluster_id and idempotency_key are required", ports.ErrInvalid)
	}
	var record ports.K8sClusterNodePoolRecord
	err := s.store.WithTenantTx(ctx, func(ctx context.Context, tx ports.MetadataTx) error {
		return scanK8sNodePoolRow(tx.QueryRow(ctx, `
			SELECT cluster_id, node_pool_id, name, node_count, instance_type,
				gpu_vendor, gpu_model, gpu_count, gpu_resource_name,
				state, reason, provider, real_provider, provider_refs, created_at, updated_at
			FROM k8s_cluster_node_pools
			WHERE tenant_id = $1::uuid AND cluster_id = $2 AND idempotency_key = $3
		`, tenantID, clusterID, idemKey), tenantID, &record)
	})
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return ports.K8sClusterNodePoolRecord{}, ports.ErrNotFound
		}
		return ports.K8sClusterNodePoolRecord{}, err
	}
	return record, nil
}

func requireK8sClusterTenant(tenantID string) error {
	if strings.TrimSpace(tenantID) == "" {
		return fmt.Errorf("%w: tenant_id is required", ports.ErrInvalid)
	}
	return nil
}

func k8sClusterUnixTimes(now func() time.Time, createdAt int64, updatedAt int64) (time.Time, time.Time) {
	current := time.Now().UTC()
	if now != nil {
		current = now().UTC()
	}
	created := current
	if createdAt > 0 {
		created = time.Unix(createdAt, 0).UTC()
	}
	updated := created
	if updatedAt > 0 {
		updated = time.Unix(updatedAt, 0).UTC()
	}
	return created, updated
}

func scanK8sClusterRow(row ports.Row, tenantID string, record *ports.K8sClusterRecord) error {
	var state string
	var refsJSON []byte
	var createdAt time.Time
	var updatedAt time.Time
	if err := row.Scan(
		&record.ClusterID, &record.Name, &record.Version, &state, &record.Reason,
		&record.Provider, &record.RealProvider, &refsJSON, &createdAt, &updatedAt,
	); err != nil {
		return err
	}
	record.TenantID = tenantID
	record.State = ports.K8sClusterState(state)
	record.ProviderRefs = decodeStringSliceJSON(refsJSON)
	record.CreatedAt = createdAt.Unix()
	record.UpdatedAt = updatedAt.Unix()
	return nil
}

func scanK8sClusterRows(rows ports.Rows, tenantID string, record *ports.K8sClusterRecord) error {
	var state string
	var refsJSON []byte
	var createdAt time.Time
	var updatedAt time.Time
	if err := rows.Scan(
		&record.ClusterID, &record.Name, &record.Version, &state, &record.Reason,
		&record.Provider, &record.RealProvider, &refsJSON, &createdAt, &updatedAt,
	); err != nil {
		return err
	}
	record.TenantID = tenantID
	record.State = ports.K8sClusterState(state)
	record.ProviderRefs = decodeStringSliceJSON(refsJSON)
	record.CreatedAt = createdAt.Unix()
	record.UpdatedAt = updatedAt.Unix()
	return nil
}

func scanK8sNodePoolRow(row ports.Row, tenantID string, record *ports.K8sClusterNodePoolRecord) error {
	var state string
	var refsJSON []byte
	var createdAt time.Time
	var updatedAt time.Time
	var gpuVendor, gpuModel, gpuResourceName *string
	if err := row.Scan(
		&record.ClusterID, &record.NodePoolID, &record.Name, &record.NodeCount, &record.InstanceType,
		&gpuVendor, &gpuModel, &record.GPU.Count, &gpuResourceName,
		&state, &record.Reason, &record.Provider, &record.RealProvider, &refsJSON, &createdAt, &updatedAt,
	); err != nil {
		return err
	}
	record.TenantID = tenantID
	record.State = ports.K8sClusterNodePoolState(state)
	record.GPU.Vendor = stringPtrValue(gpuVendor)
	record.GPU.Model = stringPtrValue(gpuModel)
	record.GPU.ResourceName = stringPtrValue(gpuResourceName)
	record.ProviderRefs = decodeStringSliceJSON(refsJSON)
	record.CreatedAt = createdAt.Unix()
	record.UpdatedAt = updatedAt.Unix()
	return nil
}

func scanK8sNodePoolRows(rows ports.Rows, tenantID string, record *ports.K8sClusterNodePoolRecord) error {
	var state string
	var refsJSON []byte
	var createdAt time.Time
	var updatedAt time.Time
	var gpuVendor, gpuModel, gpuResourceName *string
	if err := rows.Scan(
		&record.ClusterID, &record.NodePoolID, &record.Name, &record.NodeCount, &record.InstanceType,
		&gpuVendor, &gpuModel, &record.GPU.Count, &gpuResourceName,
		&state, &record.Reason, &record.Provider, &record.RealProvider, &refsJSON, &createdAt, &updatedAt,
	); err != nil {
		return err
	}
	record.TenantID = tenantID
	record.State = ports.K8sClusterNodePoolState(state)
	record.GPU.Vendor = stringPtrValue(gpuVendor)
	record.GPU.Model = stringPtrValue(gpuModel)
	record.GPU.ResourceName = stringPtrValue(gpuResourceName)
	record.ProviderRefs = decodeStringSliceJSON(refsJSON)
	record.CreatedAt = createdAt.Unix()
	record.UpdatedAt = updatedAt.Unix()
	return nil
}

func decodeStringSliceJSON(raw []byte) []string {
	if len(raw) == 0 {
		return nil
	}
	var refs []string
	if err := json.Unmarshal(raw, &refs); err != nil {
		return nil
	}
	return refs
}

func stringPtrValue(value *string) string {
	if value == nil {
		return ""
	}
	return *value
}

var _ ports.K8sClusterResourceStore = (*MetadataK8sClusterStore)(nil)
