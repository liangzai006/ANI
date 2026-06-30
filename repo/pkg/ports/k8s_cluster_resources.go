package ports

import "context"

type K8sClusterResourceStore interface {
	UpsertCluster(ctx context.Context, record K8sClusterRecord, idempotencyKey string) error
	GetCluster(ctx context.Context, tenantID, clusterID string) (K8sClusterRecord, error)
	ListClusters(ctx context.Context, tenantID string) ([]K8sClusterRecord, error)
	GetClusterByIdempotency(ctx context.Context, tenantID, idempotencyKey string) (K8sClusterRecord, error)

	UpsertNodePool(ctx context.Context, record K8sClusterNodePoolRecord, idempotencyKey string) error
	GetNodePool(ctx context.Context, tenantID, clusterID, nodePoolID string) (K8sClusterNodePoolRecord, error)
	ListNodePools(ctx context.Context, tenantID, clusterID string) ([]K8sClusterNodePoolRecord, error)
	GetNodePoolByIdempotency(ctx context.Context, tenantID, clusterID, idempotencyKey string) (K8sClusterNodePoolRecord, error)
}
