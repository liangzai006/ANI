package main

import (
	"testing"

	runtimeadapter "github.com/kubercloud/ani/pkg/adapters/runtime"
)

func TestGatewayP1ServiceFactoriesUseMetadataWhenConfigured(t *testing.T) {
	store := &gatewayK8sProxyMetadataStore{}
	if _, ok := newGatewayBrandingService(store, nil).(*runtimeadapter.MetadataBrandingService); !ok {
		t.Fatalf("branding service = %T, want MetadataBrandingService", newGatewayBrandingService(store, nil))
	}
	if _, ok := newGatewayAsyncTaskService(store).(*runtimeadapter.MetadataAsyncTaskService); !ok {
		t.Fatalf("async task service = %T, want MetadataAsyncTaskService", newGatewayAsyncTaskService(store))
	}
	if _, ok := newGatewayMeteringService(store).(*runtimeadapter.MetadataMeteringService); !ok {
		t.Fatalf("metering service = %T, want MetadataMeteringService", newGatewayMeteringService(store))
	}
	if newGatewayVectorStoreMetadataStore(store) == nil {
		t.Fatal("vector store metadata store = nil, want metadata adapter")
	}
}

func TestGatewayP1ServiceFactoriesDefaultToLocalWithoutMetadata(t *testing.T) {
	if _, ok := newGatewayBrandingService(nil, nil).(*runtimeadapter.LocalBrandingService); !ok {
		t.Fatalf("branding service = %T, want LocalBrandingService", newGatewayBrandingService(nil, nil))
	}
	if _, ok := newGatewayAsyncTaskService(nil).(*runtimeadapter.LocalAsyncTaskService); !ok {
		t.Fatalf("async task service = %T, want LocalAsyncTaskService", newGatewayAsyncTaskService(nil))
	}
	if _, ok := newGatewayMeteringService(nil).(*runtimeadapter.LocalMeteringService); !ok {
		t.Fatalf("metering service = %T, want LocalMeteringService", newGatewayMeteringService(nil))
	}
	if newGatewayVectorStoreMetadataStore(nil) != nil {
		t.Fatal("vector store metadata store != nil, want nil without metadata")
	}
}

func TestGatewayVectorStoreServiceUsesMetadataStoreWithoutMilvusProvider(t *testing.T) {
	store := &gatewayK8sProxyMetadataStore{}
	service, err := newGatewayVectorStoreService(gatewayVectorStoreRuntimeConfig{}, store)
	if err != nil {
		t.Fatalf("newGatewayVectorStoreService() error = %v", err)
	}
	if service == nil {
		t.Fatal("service = nil, want metadata-backed local vector store service")
	}
}
