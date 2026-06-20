package main

import (
	"fmt"
	"net/http"
	"os"
	"strings"

	runtimeadapter "github.com/kubercloud/ani/pkg/adapters/runtime"
	"github.com/kubercloud/ani/pkg/adapters/vectorstore"
	"github.com/kubercloud/ani/pkg/ports"
)

type gatewayVectorStoreRuntimeConfig struct {
	VectorStoreProvider         string
	VectorStoreEndpoint         string
	VectorStoreToken            string
	VectorStoreDatabase         string
	VectorStoreCollectionPrefix string
	VectorStoreHTTPClient       *http.Client
}

func gatewayVectorStoreRuntimeConfigFromEnv() gatewayVectorStoreRuntimeConfig {
	return gatewayVectorStoreRuntimeConfig{
		VectorStoreProvider:         os.Getenv("VECTOR_STORE_PROVIDER"),
		VectorStoreEndpoint:         os.Getenv("VECTOR_STORE_ENDPOINT"),
		VectorStoreToken:            os.Getenv("VECTOR_STORE_TOKEN"),
		VectorStoreDatabase:         os.Getenv("VECTOR_STORE_DATABASE"),
		VectorStoreCollectionPrefix: os.Getenv("VECTOR_STORE_COLLECTION_PREFIX"),
	}
}

func newGatewayVectorStoreService(cfg gatewayVectorStoreRuntimeConfig) (ports.VectorStoreService, error) {
	switch provider := strings.TrimSpace(cfg.VectorStoreProvider); provider {
	case "", "local", "not_configured":
		return nil, nil
	case "milvus":
		store, err := vectorstore.NewMilvusVectorStore(vectorstore.MilvusVectorStoreConfig{
			Endpoint:         cfg.VectorStoreEndpoint,
			Token:            cfg.VectorStoreToken,
			Database:         cfg.VectorStoreDatabase,
			CollectionPrefix: cfg.VectorStoreCollectionPrefix,
			HTTPClient:       cfg.VectorStoreHTTPClient,
		})
		if err != nil {
			return nil, err
		}
		return runtimeadapter.NewLocalVectorStoreService(runtimeadapter.WithVectorStoreBackend(store)), nil
	default:
		return nil, fmt.Errorf("%w: unsupported VECTOR_STORE_PROVIDER %q", ports.ErrUnsupported, provider)
	}
}
