package main

import (
	"context"
	"os"
	"strings"

	runtimeadapter "github.com/kubercloud/ani/pkg/adapters/runtime"
	"github.com/kubercloud/ani/pkg/bootstrap"
	"github.com/kubercloud/ani/pkg/ports"
)

func gatewayDatabaseURLFromEnv() string {
	return strings.TrimSpace(os.Getenv("DATABASE_URL"))
}

func gatewayHTTPAddrFromEnv() string {
	if value := strings.TrimSpace(os.Getenv("GATEWAY_HTTP_ADDR")); value != "" {
		return value
	}
	return ":8080"
}

func connectGatewayMetadataStore(ctx context.Context) (ports.MetadataStore, func(), error) {
	closeStore := func() {}
	databaseURL := gatewayDatabaseURLFromEnv()
	if databaseURL == "" {
		return nil, closeStore, nil
	}
	store, closeFn, err := bootstrap.ConnectMetadataStore(ctx, databaseURL)
	if err != nil {
		return nil, closeStore, err
	}
	return store, closeFn, nil
}

func newGatewayAsyncTaskService(store ports.MetadataStore) ports.AsyncTaskService {
	if store == nil {
		return runtimeadapter.NewLocalAsyncTaskService()
	}
	return runtimeadapter.NewMetadataAsyncTaskService(store)
}

func newGatewayMeteringService(store ports.MetadataStore) ports.MeteringService {
	if store == nil {
		return runtimeadapter.NewLocalMeteringService()
	}
	return runtimeadapter.NewMetadataMeteringService(store)
}

func newGatewayVectorStoreMetadataStore(store ports.MetadataStore) ports.VectorStoreMetadataStore {
	if store == nil {
		return nil
	}
	return runtimeadapter.NewMetadataVectorStoreMetadataStore(store)
}
