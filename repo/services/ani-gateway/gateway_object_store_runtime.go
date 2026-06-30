package main

import (
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/kubercloud/ani/pkg/adapters/objectstore"
	"github.com/kubercloud/ani/pkg/ports"
)

type gatewayObjectStoreRuntimeConfig struct {
	Provider               string
	Endpoint               string
	Endpoints              []string
	PublicEndpoint         string
	AccessKeyID            string
	SecretAccessKey        string
	SessionToken           string
	Region                 string
	Secure                 bool
	BucketPrefix           string
	HTTPClient             *http.Client
	RequestTimeout         time.Duration
}

func gatewayObjectStoreRuntimeConfigFromEnv() gatewayObjectStoreRuntimeConfig {
	return gatewayObjectStoreRuntimeConfig{
		Provider:               os.Getenv("OBJECT_STORE_PROVIDER"),
		Endpoint:               os.Getenv("OBJECT_STORE_ENDPOINT"),
		Endpoints:              splitGatewayCSVEnv(os.Getenv("OBJECT_STORE_ENDPOINTS")),
		PublicEndpoint:         os.Getenv("OBJECT_STORE_PUBLIC_ENDPOINT"),
		AccessKeyID:            os.Getenv("OBJECT_STORE_ACCESS_KEY_ID"),
		SecretAccessKey:        os.Getenv("OBJECT_STORE_SECRET_ACCESS_KEY"),
		SessionToken:           os.Getenv("OBJECT_STORE_SESSION_TOKEN"),
		Region:                 os.Getenv("OBJECT_STORE_REGION"),
		Secure:                 strings.EqualFold(strings.TrimSpace(os.Getenv("OBJECT_STORE_SECURE")), "true"),
		BucketPrefix:           os.Getenv("OBJECT_STORE_BUCKET_PREFIX"),
		RequestTimeout:         gatewayDurationFromEnv("OBJECT_STORE_REQUEST_TIMEOUT"),
	}
}

func newGatewayObjectStore(cfg gatewayObjectStoreRuntimeConfig) (ports.ObjectStore, error) {
	if strings.TrimSpace(cfg.Provider) != "minio" {
		return nil, nil
	}
	return objectstore.NewMinIOObjectStore(objectstore.MinIOObjectStoreConfig{
		Endpoint:        cfg.Endpoint,
		Endpoints:       cfg.Endpoints,
		PublicEndpoint:  cfg.PublicEndpoint,
		AccessKeyID:     cfg.AccessKeyID,
		SecretAccessKey: cfg.SecretAccessKey,
		SessionToken:    cfg.SessionToken,
		Region:          cfg.Region,
		Secure:          cfg.Secure,
		BucketPrefix:    cfg.BucketPrefix,
		HTTPClient:      cfg.HTTPClient,
		RequestTimeout:  cfg.RequestTimeout,
	})
}

func newGatewayObjectStoreFromEnv() (ports.ObjectStore, error) {
	store, err := newGatewayObjectStore(gatewayObjectStoreRuntimeConfigFromEnv())
	if err != nil {
		return nil, fmt.Errorf("configure gateway object store: %w", err)
	}
	return store, nil
}
