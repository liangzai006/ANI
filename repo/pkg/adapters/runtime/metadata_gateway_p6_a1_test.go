package runtime

import (
	"context"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/kubercloud/ani/pkg/ports"
)

const k8sClusterStoreTenantID = "00000000-0000-0000-0000-000000000001"

func TestMetadataK8sClusterStoreUpsertsCluster(t *testing.T) {
	tx := &fakeMetadataTx{}
	store := NewMetadataK8sClusterStore(fakeMetadataStore{tx: tx}, WithK8sClusterStoreClock(func() time.Time {
		return time.Unix(200, 0).UTC()
	}))
	err := store.UpsertCluster(context.Background(), ports.K8sClusterRecord{
		TenantID:  k8sClusterStoreTenantID,
		ClusterID: "k8sclu-test",
		Name:      "lab-cluster",
		Version:   "1.29.0",
		State:     ports.K8sClusterStateRunning,
		Reason:    "local vcluster profile",
		Provider:  "local",
		CreatedAt: 200,
		UpdatedAt: 200,
	}, "idem-k8s-cluster")
	if err != nil {
		t.Fatalf("UpsertCluster() error = %v", err)
	}
	if !strings.Contains(tx.sql, "INSERT INTO k8s_clusters") {
		t.Fatalf("sql = %q, want k8s_clusters insert", tx.sql)
	}
}

func TestMetadataK8sClusterStoreListClustersUsesTenantScopedQuery(t *testing.T) {
	tx := &fakeMetadataTx{
		queryRows: []ports.Row{
			k8sClusterFakeRow{record: ports.K8sClusterRecord{
				TenantID:  k8sClusterStoreTenantID,
				ClusterID: "k8sclu-list",
				Name:      "list-cluster",
				Version:   "1.29.0",
				State:     ports.K8sClusterStateRunning,
				Provider:  "local",
				CreatedAt: 1,
				UpdatedAt: 2,
			}},
		},
	}
	store := NewMetadataK8sClusterStore(fakeMetadataStore{tx: tx})
	records, err := store.ListClusters(context.Background(), k8sClusterStoreTenantID)
	if err != nil {
		t.Fatalf("ListClusters() error = %v", err)
	}
	if len(records) != 1 || records[0].ClusterID != "k8sclu-list" {
		t.Fatalf("records = %#v, want one cluster", records)
	}
	if !strings.Contains(tx.querySQL, "FROM k8s_clusters") {
		t.Fatalf("querySQL = %q, want k8s_clusters select", tx.querySQL)
	}
}

func TestMetadataK8sClusterStoreUpsertsNodePool(t *testing.T) {
	tx := &fakeMetadataTx{}
	store := NewMetadataK8sClusterStore(fakeMetadataStore{tx: tx})
	err := store.UpsertNodePool(context.Background(), ports.K8sClusterNodePoolRecord{
		TenantID:     k8sClusterStoreTenantID,
		ClusterID:    "k8sclu-test",
		NodePoolID:   "k8snp-test",
		Name:         "default-pool",
		NodeCount:    2,
		InstanceType: "standard-4",
		State:        ports.K8sClusterNodePoolStateRunning,
		Provider:     "local",
		CreatedAt:    300,
		UpdatedAt:    300,
	}, "idem-k8s-node-pool")
	if err != nil {
		t.Fatalf("UpsertNodePool() error = %v", err)
	}
	if !strings.Contains(tx.sql, "INSERT INTO k8s_cluster_node_pools") {
		t.Fatalf("sql = %q, want k8s_cluster_node_pools insert", tx.sql)
	}
}

func TestLocalK8sClusterServiceGetClusterReadsFromMetadataStore(t *testing.T) {
	tx := &fakeMetadataTx{
		row: k8sClusterFakeRow{record: ports.K8sClusterRecord{
			TenantID:  k8sClusterStoreTenantID,
			ClusterID: "k8sclu-restart",
			Name:      "restart-cluster",
			Version:   "1.29.0",
			State:     ports.K8sClusterStateRunning,
			Provider:  "local",
			CreatedAt: 300,
			UpdatedAt: 300,
		}},
	}
	store := NewMetadataK8sClusterStore(fakeMetadataStore{tx: tx})
	service := NewLocalK8sClusterService(WithK8sClusterResourceStore(store))
	got, err := service.GetCluster(context.Background(), ports.K8sClusterGetRequest{
		TenantID:  k8sClusterStoreTenantID,
		ClusterID: "k8sclu-restart",
	})
	if err != nil {
		t.Fatalf("GetCluster() error = %v", err)
	}
	if got.Name != "restart-cluster" {
		t.Fatalf("name = %q, want restart-cluster", got.Name)
	}
}

func TestLocalK8sClusterServiceListNodePoolsReadsFromMetadataStore(t *testing.T) {
	clusterTx := &fakeMetadataTx{
		row: k8sClusterFakeRow{record: ports.K8sClusterRecord{
			TenantID:  k8sClusterStoreTenantID,
			ClusterID: "k8sclu-parent",
			Name:      "parent-cluster",
			Version:   "1.29.0",
			State:     ports.K8sClusterStateRunning,
			Provider:  "local",
			CreatedAt: 100,
			UpdatedAt: 100,
		}},
	}
	nodePoolTx := &fakeMetadataTx{
		queryRows: []ports.Row{
			k8sNodePoolFakeRow{record: ports.K8sClusterNodePoolRecord{
				TenantID:     k8sClusterStoreTenantID,
				ClusterID:    "k8sclu-parent",
				NodePoolID:   "k8snp-list",
				Name:         "pool-a",
				NodeCount:    3,
				InstanceType: "standard-8",
				State:        ports.K8sClusterNodePoolStateRunning,
				Provider:     "local",
				CreatedAt:    200,
				UpdatedAt:    200,
			}},
		},
	}
	store := &sequentialK8sClusterMetadataStore{steps: []ports.MetadataStore{
		fakeMetadataStore{tx: clusterTx},
		fakeMetadataStore{tx: nodePoolTx},
	}}
	service := NewLocalK8sClusterService(WithK8sClusterResourceStore(NewMetadataK8sClusterStore(store)))
	pools, err := service.ListNodePools(context.Background(), ports.K8sClusterNodePoolListRequest{
		TenantID:  k8sClusterStoreTenantID,
		ClusterID: "k8sclu-parent",
	})
	if err != nil {
		t.Fatalf("ListNodePools() error = %v", err)
	}
	if len(pools) != 1 || pools[0].NodePoolID != "k8snp-list" {
		t.Fatalf("pools = %#v, want one node pool", pools)
	}
}

type k8sClusterFakeRow struct {
	record ports.K8sClusterRecord
}

func (r k8sClusterFakeRow) Scan(dest ...any) error {
	state := string(r.record.State)
	refsJSON := []byte("[]")
	createdAt := time.Unix(r.record.CreatedAt, 0).UTC()
	updatedAt := time.Unix(r.record.UpdatedAt, 0).UTC()
	*dest[0].(*string) = r.record.ClusterID
	*dest[1].(*string) = r.record.Name
	*dest[2].(*string) = r.record.Version
	*dest[3].(*string) = state
	*dest[4].(*string) = r.record.Reason
	*dest[5].(*string) = r.record.Provider
	*dest[6].(*bool) = r.record.RealProvider
	*dest[7].(*[]byte) = refsJSON
	*dest[8].(*time.Time) = createdAt
	*dest[9].(*time.Time) = updatedAt
	return nil
}

type k8sNodePoolFakeRow struct {
	record ports.K8sClusterNodePoolRecord
}

func (r k8sNodePoolFakeRow) Scan(dest ...any) error {
	state := string(r.record.State)
	refsJSON := []byte("[]")
	createdAt := time.Unix(r.record.CreatedAt, 0).UTC()
	updatedAt := time.Unix(r.record.UpdatedAt, 0).UTC()
	gpuVendor := optionalStringPtr(r.record.GPU.Vendor)
	gpuModel := optionalStringPtr(r.record.GPU.Model)
	gpuResourceName := optionalStringPtr(r.record.GPU.ResourceName)
	*dest[0].(*string) = r.record.ClusterID
	*dest[1].(*string) = r.record.NodePoolID
	*dest[2].(*string) = r.record.Name
	*dest[3].(*int) = r.record.NodeCount
	*dest[4].(*string) = r.record.InstanceType
	*dest[5].(**string) = gpuVendor
	*dest[6].(**string) = gpuModel
	*dest[7].(*int) = r.record.GPU.Count
	*dest[8].(**string) = gpuResourceName
	*dest[9].(*string) = state
	*dest[10].(*string) = r.record.Reason
	*dest[11].(*string) = r.record.Provider
	*dest[12].(*bool) = r.record.RealProvider
	*dest[13].(*[]byte) = refsJSON
	*dest[14].(*time.Time) = createdAt
	*dest[15].(*time.Time) = updatedAt
	return nil
}

func optionalStringPtr(value string) *string {
	if value == "" {
		return nil
	}
	v := value
	return &v
}

type sequentialK8sClusterMetadataStore struct {
	steps []ports.MetadataStore
	index int
}

func (s *sequentialK8sClusterMetadataStore) Ping(context.Context) error { return nil }

func (s *sequentialK8sClusterMetadataStore) WithTenantTx(ctx context.Context, fn func(context.Context, ports.MetadataTx) error) error {
	if s.index >= len(s.steps) {
		return fmt.Errorf("no metadata store step configured")
	}
	store := s.steps[s.index]
	s.index++
	return store.WithTenantTx(ctx, fn)
}

func (s *sequentialK8sClusterMetadataStore) WithPlatformTx(ctx context.Context, fn func(context.Context, ports.MetadataTx) error) error {
	return fmt.Errorf("platform tx not supported in test")
}
