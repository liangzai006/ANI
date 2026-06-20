package runtime

import (
	"context"
	"fmt"
	"strings"

	"github.com/google/uuid"
	"github.com/kubercloud/ani/pkg/ports"
	"github.com/kubercloud/ani/pkg/types"
)

type MetadataK8sClusterProxyTargetStore struct {
	store ports.MetadataStore
}

func NewMetadataK8sClusterProxyTargetStore(store ports.MetadataStore) *MetadataK8sClusterProxyTargetStore {
	return &MetadataK8sClusterProxyTargetStore{store: store}
}

func (s *MetadataK8sClusterProxyTargetStore) UpsertK8sClusterProxyTarget(ctx context.Context, target ports.K8sClusterProxyTarget) error {
	if s.store == nil {
		return ports.ErrNotConfigured
	}
	if err := validateK8sClusterProxyTarget(target); err != nil {
		return err
	}
	target = cloneK8sClusterProxyTarget(target)
	tenantCtx, err := k8sProxyMetadataTenantContext(ctx, target.TenantID)
	if err != nil {
		return err
	}
	return s.store.WithTenantTx(tenantCtx, func(ctx context.Context, tx ports.MetadataTx) error {
		_, err := tx.Exec(ctx, `
			INSERT INTO k8s_cluster_proxy_targets (tenant_id, cluster_id, server, bearer_token, ca_data, client_certificate_data, client_key_data, updated_at)
			VALUES ($1::uuid, $2, $3, NULLIF($4, ''), NULLIF($5, ''), NULLIF($6, ''), NULLIF($7, ''), NOW())
			ON CONFLICT (tenant_id, cluster_id) DO UPDATE SET
				server = EXCLUDED.server,
				bearer_token = EXCLUDED.bearer_token,
				ca_data = EXCLUDED.ca_data,
				client_certificate_data = EXCLUDED.client_certificate_data,
				client_key_data = EXCLUDED.client_key_data,
				updated_at = EXCLUDED.updated_at
		`, target.TenantID, target.ClusterID, target.Server, target.BearerToken, target.CAData, target.ClientCertificateData, target.ClientKeyData)
		if err != nil {
			return fmt.Errorf("upsert k8s cluster proxy target: %w", err)
		}
		return nil
	})
}

func (s *MetadataK8sClusterProxyTargetStore) ResolveK8sClusterProxyTarget(ctx context.Context, req ports.K8sClusterGetRequest) (ports.K8sClusterProxyTarget, error) {
	if s.store == nil {
		return ports.K8sClusterProxyTarget{}, ports.ErrNotConfigured
	}
	if strings.TrimSpace(req.TenantID) == "" || strings.TrimSpace(req.ClusterID) == "" {
		return ports.K8sClusterProxyTarget{}, fmt.Errorf("%w: tenant_id/cluster_id required for k8s proxy target lookup", ports.ErrInvalid)
	}

	var target ports.K8sClusterProxyTarget
	tenantCtx, err := k8sProxyMetadataTenantContext(ctx, req.TenantID)
	if err != nil {
		return ports.K8sClusterProxyTarget{}, err
	}
	err = s.store.WithTenantTx(tenantCtx, func(ctx context.Context, tx ports.MetadataTx) error {
		row := tx.QueryRow(ctx, `
			SELECT tenant_id::text, cluster_id, server, COALESCE(bearer_token, ''), COALESCE(ca_data, ''), COALESCE(client_certificate_data, ''), COALESCE(client_key_data, '')
			FROM k8s_cluster_proxy_targets
			WHERE tenant_id = $1::uuid AND cluster_id = $2
		`, req.TenantID, req.ClusterID)
		return row.Scan(&target.TenantID, &target.ClusterID, &target.Server, &target.BearerToken, &target.CAData, &target.ClientCertificateData, &target.ClientKeyData)
	})
	if err != nil {
		return ports.K8sClusterProxyTarget{}, err
	}
	return cloneK8sClusterProxyTarget(target), nil
}

func (s *MetadataK8sClusterProxyTargetStore) DeleteK8sClusterProxyTarget(ctx context.Context, req ports.K8sClusterGetRequest) error {
	if s.store == nil {
		return ports.ErrNotConfigured
	}
	if strings.TrimSpace(req.TenantID) == "" || strings.TrimSpace(req.ClusterID) == "" {
		return fmt.Errorf("%w: tenant_id/cluster_id required for k8s proxy target delete", ports.ErrInvalid)
	}
	tenantCtx, err := k8sProxyMetadataTenantContext(ctx, req.TenantID)
	if err != nil {
		return err
	}
	return s.store.WithTenantTx(tenantCtx, func(ctx context.Context, tx ports.MetadataTx) error {
		_, err := tx.Exec(ctx, `
			DELETE FROM k8s_cluster_proxy_targets
			WHERE tenant_id = $1::uuid AND cluster_id = $2
		`, req.TenantID, req.ClusterID)
		if err != nil {
			return fmt.Errorf("delete k8s cluster proxy target: %w", err)
		}
		return nil
	})
}

func k8sProxyMetadataTenantContext(ctx context.Context, tenantID string) (context.Context, error) {
	if _, ok := types.TryFromContext(ctx); ok {
		return ctx, nil
	}
	parsed, err := uuid.Parse(strings.TrimSpace(tenantID))
	if err != nil {
		return nil, fmt.Errorf("%w: metadata-backed k8s proxy target requires UUID tenant_id", ports.ErrInvalid)
	}
	return types.WithTenant(ctx, &types.TenantContext{TenantID: parsed}), nil
}

var _ ports.K8sClusterProxyTargetStore = (*MetadataK8sClusterProxyTargetStore)(nil)
