package router

import (
	"context"
	"testing"

	"github.com/kubercloud/ani/pkg/ports"
)

type recordingVectorStoreService struct {
	createCalls int
}

func (s *recordingVectorStoreService) CreateVectorStore(_ context.Context, request ports.VectorStoreCreateRequest) (ports.VectorStoreRecord, error) {
	s.createCalls++
	return ports.VectorStoreRecord{
		TenantID:  request.TenantID,
		StoreID:   "vst_injected",
		Name:      request.Name,
		Dimension: request.Dimension,
		Metric:    request.Metric,
		State:     ports.VectorStoreReady,
	}, nil
}

func (s *recordingVectorStoreService) ListVectorStores(context.Context, ports.VectorStoreResourceListRequest) ([]ports.VectorStoreRecord, error) {
	return nil, nil
}

func (s *recordingVectorStoreService) GetVectorStore(context.Context, ports.VectorStoreResourceGetRequest) (ports.VectorStoreRecord, error) {
	return ports.VectorStoreRecord{}, ports.ErrNotFound
}

func (s *recordingVectorStoreService) DeleteVectorStore(context.Context, ports.VectorStoreResourceGetRequest) (ports.VectorStoreRecord, error) {
	return ports.VectorStoreRecord{}, ports.ErrNotFound
}

func (s *recordingVectorStoreService) SearchVectorStore(context.Context, ports.VectorStoreResourceSearchRequest) ([]ports.VectorSearchResult, error) {
	return nil, nil
}

func (s *recordingVectorStoreService) InsertDocuments(context.Context, ports.VectorStoreDocumentInsertRequest) (ports.VectorStoreDocumentInsertResult, error) {
	return ports.VectorStoreDocumentInsertResult{}, nil
}

func TestVectorStoreAPIDevProfileCreateSearchAndDelete(t *testing.T) {
	api := newVectorStoreAPI()
	store, err := api.service.CreateVectorStore(context.Background(), ports.VectorStoreCreateRequest{
		TenantID:       "tenant-a",
		IdempotencyKey: "api-vector-a",
		Name:           "kb-main",
		Dimension:      3,
		Metric:         "cosine",
	})
	if err != nil {
		t.Fatalf("CreateVectorStore error = %v", err)
	}
	if got := vectorStoreFromRecord(store); got.ID == "" || got.State != "ready" || got.Dimension != 3 {
		t.Fatalf("vector store response = %+v, want ready vector store", got)
	} else {
		requireLocalCoreDevProfile(t, got.DevProfile, "local-vector-store-service")
	}
	results, err := api.service.SearchVectorStore(context.Background(), ports.VectorStoreResourceSearchRequest{
		TenantID:   "tenant-a",
		ResourceID: store.StoreID,
		Vector:     []float32{0.1, 0.2, 0.3},
		TopK:       5,
	})
	if err != nil {
		t.Fatalf("SearchVectorStore error = %v", err)
	}
	if len(results) != 0 {
		t.Fatalf("results = %d, want empty dev profile search result", len(results))
	}
	deleted, err := api.service.DeleteVectorStore(context.Background(), ports.VectorStoreResourceGetRequest{
		TenantID:   "tenant-a",
		ResourceID: store.StoreID,
	})
	if err != nil {
		t.Fatalf("DeleteVectorStore error = %v", err)
	}
	if deleted.State != ports.VectorStoreDeleted {
		t.Fatalf("deleted state = %q, want deleted", deleted.State)
	}
}

func TestVectorStoreAPIServiceKeepsTenantIsolation(t *testing.T) {
	api := newVectorStoreAPI()
	store, err := api.service.CreateVectorStore(context.Background(), ports.VectorStoreCreateRequest{
		TenantID:       "tenant-a",
		IdempotencyKey: "api-vector-b",
		Name:           "tenant-a-store",
		Dimension:      3,
	})
	if err != nil {
		t.Fatalf("CreateVectorStore error = %v", err)
	}
	if _, err := api.service.GetVectorStore(context.Background(), ports.VectorStoreResourceGetRequest{
		TenantID:   "tenant-b",
		ResourceID: store.StoreID,
	}); err == nil {
		t.Fatalf("GetVectorStore from another tenant succeeded, want isolation error")
	}
}

func TestVectorStoreAPIDocumentInsertResponseMatchesCoreSchema(t *testing.T) {
	api := newVectorStoreAPI()
	store, err := api.service.CreateVectorStore(context.Background(), ports.VectorStoreCreateRequest{
		TenantID:       "tenant-a",
		IdempotencyKey: "api-vector-docs",
		Name:           "kb-main",
		Dimension:      3,
	})
	if err != nil {
		t.Fatalf("CreateVectorStore error = %v", err)
	}

	result, err := api.service.InsertDocuments(context.Background(), ports.VectorStoreDocumentInsertRequest{
		TenantID:       "tenant-a",
		ResourceID:     store.StoreID,
		IdempotencyKey: "api-insert-docs",
		Documents: []ports.VectorDocumentInput{
			{ID: "doc-a", Content: "hello vector", Metadata: map[string]string{"source": "router"}},
		},
	})
	if err != nil {
		t.Fatalf("InsertDocuments error = %v", err)
	}
	if got := vectorStoreDocumentInsertFromResult(result); got.InsertedCount != 1 || got.TaskID == "" || got.Status != "completed" {
		t.Fatalf("insert response = %+v, want VectorStoreDocumentInsertResponse fields", got)
	}
}

func TestVectorStoreAPIUsesInjectedService(t *testing.T) {
	service := &recordingVectorStoreService{}
	api := newVectorStoreAPIWithService(service)
	store, err := api.service.CreateVectorStore(context.Background(), ports.VectorStoreCreateRequest{
		TenantID:       "tenant-a",
		IdempotencyKey: "api-vector-injected",
		Name:           "kb-injected",
		Dimension:      3,
		Metric:         "cosine",
	})
	if err != nil {
		t.Fatalf("CreateVectorStore error = %v", err)
	}
	if service.createCalls != 1 || store.StoreID != "vst_injected" {
		t.Fatalf("injected service createCalls=%d store=%+v, want injected service", service.createCalls, store)
	}
}
