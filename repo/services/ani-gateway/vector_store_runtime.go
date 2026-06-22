package main

import (
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	runtimeadapter "github.com/kubercloud/ani/pkg/adapters/runtime"
	"github.com/kubercloud/ani/pkg/adapters/vectorstore"
	"github.com/kubercloud/ani/pkg/ports"
)

type gatewayVectorStoreRuntimeConfig struct {
	VectorStoreProvider         string
	VectorStoreEndpoint         string
	VectorStoreEndpoints        []string
	VectorStoreToken            string
	VectorStoreDatabase         string
	VectorStoreCollectionPrefix string
	VectorStoreHTTPClient       *http.Client
	VectorStoreRequestTimeout   time.Duration
}

func gatewayVectorStoreRuntimeConfigFromEnv() gatewayVectorStoreRuntimeConfig {
	return gatewayVectorStoreRuntimeConfig{
		VectorStoreProvider:         os.Getenv("VECTOR_STORE_PROVIDER"),
		VectorStoreEndpoint:         os.Getenv("VECTOR_STORE_ENDPOINT"),
		VectorStoreEndpoints:        splitGatewayCSVEnv(os.Getenv("VECTOR_STORE_ENDPOINTS")),
		VectorStoreToken:            os.Getenv("VECTOR_STORE_TOKEN"),
		VectorStoreDatabase:         os.Getenv("VECTOR_STORE_DATABASE"),
		VectorStoreCollectionPrefix: os.Getenv("VECTOR_STORE_COLLECTION_PREFIX"),
		VectorStoreRequestTimeout:   gatewayDurationFromEnv("VECTOR_STORE_REQUEST_TIMEOUT"),
	}
}

func newGatewayVectorStoreService(cfg gatewayVectorStoreRuntimeConfig) (ports.VectorStoreService, error) {
	switch provider := strings.TrimSpace(cfg.VectorStoreProvider); provider {
	case "", "local", "not_configured":
		return nil, nil
	case "milvus":
		store, err := vectorstore.NewMilvusVectorStore(vectorstore.MilvusVectorStoreConfig{
			Endpoint:         cfg.VectorStoreEndpoint,
			Endpoints:        cfg.VectorStoreEndpoints,
			Token:            cfg.VectorStoreToken,
			Database:         cfg.VectorStoreDatabase,
			CollectionPrefix: cfg.VectorStoreCollectionPrefix,
			HTTPClient:       cfg.VectorStoreHTTPClient,
			RequestTimeout:   cfg.VectorStoreRequestTimeout,
		})
		if err != nil {
			return nil, err
		}
		return runtimeadapter.NewLocalVectorStoreService(runtimeadapter.WithVectorStoreBackend(store)), nil
	default:
		return nil, fmt.Errorf("%w: unsupported VECTOR_STORE_PROVIDER %q", ports.ErrUnsupported, provider)
	}
}
