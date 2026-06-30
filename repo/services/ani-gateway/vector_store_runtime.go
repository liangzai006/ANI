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

func newGatewayVectorStoreService(cfg gatewayVectorStoreRuntimeConfig, metadataStore ports.MetadataStore) (ports.VectorStoreService, error) {
	metadataOptions := []runtimeadapter.VectorStoreServiceOption{}
	if metadataStore := newGatewayVectorStoreMetadataStore(metadataStore); metadataStore != nil {
		metadataOptions = append(metadataOptions, runtimeadapter.WithVectorStoreMetadataStore(metadataStore))
	}
	switch provider := strings.TrimSpace(cfg.VectorStoreProvider); provider {
	case "", "local", "not_configured":
		if len(metadataOptions) == 0 {
			return nil, nil
		}
		return runtimeadapter.NewLocalVectorStoreService(metadataOptions...), nil
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
		metadataOptions = append(metadataOptions, runtimeadapter.WithVectorStoreBackend(store))
		return runtimeadapter.NewLocalVectorStoreService(metadataOptions...), nil
	default:
		return nil, fmt.Errorf("%w: unsupported VECTOR_STORE_PROVIDER %q", ports.ErrUnsupported, provider)
	}
}
