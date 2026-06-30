package main

import (
	"net/http"
	"time"

	runtimeadapter "github.com/kubercloud/ani/pkg/adapters/runtime"
)

func gatewayKubernetesRESTClientConfig(httpClient *http.Client, requestTimeout time.Duration) runtimeadapter.KubernetesRESTClientConfig {
	cfg := runtimeadapter.LoadKubernetesRESTEnvFromOS().ClientConfig()
	if httpClient != nil {
		cfg.HTTPClient = httpClient
	}
	if requestTimeout > 0 {
		cfg.RequestTimeout = requestTimeout
	}
	return cfg
}

func newGatewayKubernetesRESTClient(httpClient *http.Client, requestTimeout time.Duration) (*runtimeadapter.KubernetesRESTClient, error) {
	return runtimeadapter.NewKubernetesRESTClient(gatewayKubernetesRESTClientConfig(httpClient, requestTimeout))
}
