package main

import (
	"context"
	"io"
	"net/http"
	"strings"
	"testing"

	"github.com/kubercloud/ani/pkg/ports"
)

func TestGatewayNetworkServiceFromConfigDefaultsToRouterLocalService(t *testing.T) {
	service, err := newGatewayNetworkService(gatewayNetworkRuntimeConfig{}, nil)
	if err != nil {
		t.Fatalf("newGatewayNetworkService() error = %v", err)
	}
	if service != nil {
		t.Fatalf("service = %T, want nil so router keeps local default", service)
	}
}

func TestGatewayNetworkServiceFromConfigUsesKubeOVNProvider(t *testing.T) {
	t.Setenv("KUBERNETES_CONFIG_AUTO_LOAD", "false")
	t.Setenv("KUBERNETES_API_HOST", "https://kubernetes.example.test")

	transport := &gatewayNetworkRoundTripper{}
	service, err := newGatewayNetworkService(gatewayNetworkRuntimeConfig{
		ProviderMode:         "kubeovn_rest",
		ProviderApply:        true,
		ProviderUserID:       "ani-core-network-provider",
		ProviderProof:        "rbac-scope:networks.write",
		KubernetesHTTPClient: &http.Client{Transport: transport},
	}, nil)
	if err != nil {
		t.Fatalf("newGatewayNetworkService() error = %v", err)
	}
	if service == nil {
		t.Fatalf("service = nil, want provider-backed network service")
	}
	vpc, err := service.CreateVPC(context.Background(), ports.NetworkVPCCreateRequest{
		TenantID:       "tenant-a",
		IdempotencyKey: "network-vpc-a",
		Name:           "tenant-a-vpc",
	})
	if err != nil {
		t.Fatalf("CreateVPC() error = %v", err)
	}
	route, err := service.CreateRoute(context.Background(), ports.NetworkRouteCreateRequest{
		TenantID:        "tenant-a",
		IdempotencyKey:  "network-route-a",
		VPCID:           vpc.VPCID,
		DestinationCIDR: "10.250.0.0/16",
		NextHopType:     "gateway",
		NextHopID:       "10.244.180.1",
	})
	if err != nil {
		t.Fatalf("CreateRoute() error = %v", err)
	}
	if route.State != ports.NetworkResourceAvailable {
		t.Fatalf("route state = %s, want available from Kube-OVN observe", route.State)
	}
	if transport.postCalls != 0 || transport.patchCalls != 4 || transport.getCalls != 2 {
		t.Fatalf("transport post=%d patch=%d get=%d, want VPC + route dry-run/apply PATCH and observe", transport.postCalls, transport.patchCalls, transport.getCalls)
	}
}

func TestGatewayNetworkServiceRejectsKubeOVNProviderWithoutProof(t *testing.T) {
	t.Setenv("KUBERNETES_CONFIG_AUTO_LOAD", "false")
	t.Setenv("KUBERNETES_API_HOST", "https://kubernetes.example.test")

	if _, err := newGatewayNetworkService(gatewayNetworkRuntimeConfig{
		ProviderMode: "kubeovn_rest",
	}, nil); err == nil {
		t.Fatalf("newGatewayNetworkService() error = nil, want missing proof error")
	}
}

func TestGatewayNetworkConfigFromEnvLoadsProviderMode(t *testing.T) {
	t.Setenv("NETWORK_PROVIDER", "kubeovn_rest")

	cfg := gatewayNetworkRuntimeConfigFromEnv()
	if cfg.ProviderMode != "kubeovn_rest" {
		t.Fatalf("provider mode = %q, want kubeovn_rest", cfg.ProviderMode)
	}
}

type gatewayNetworkRoundTripper struct {
	postCalls  int
	patchCalls int
	getCalls   int
}

func (t *gatewayNetworkRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	if !strings.Contains(req.URL.Path, "/apis/kubeovn.io/v1/vpcs") {
		return &http.Response{StatusCode: http.StatusNotFound, Body: io.NopCloser(strings.NewReader(`{"message":"not found"}`)), Header: http.Header{}}, nil
	}
	switch req.Method {
	case http.MethodPost:
		t.postCalls++
		return &http.Response{StatusCode: http.StatusOK, Body: io.NopCloser(strings.NewReader(`{"kind":"Vpc"}`)), Header: http.Header{}}, nil
	case http.MethodPatch:
		t.patchCalls++
		return &http.Response{StatusCode: http.StatusOK, Body: io.NopCloser(strings.NewReader(`{"kind":"Vpc"}`)), Header: http.Header{}}, nil
	case http.MethodGet:
		t.getCalls++
		return &http.Response{
			StatusCode: http.StatusOK,
			Body:       io.NopCloser(strings.NewReader(`{"kind":"Vpc","status":{"conditions":[{"type":"Ready","status":"True"}]}}`)),
			Header:     http.Header{},
		}, nil
	default:
		return &http.Response{StatusCode: http.StatusMethodNotAllowed, Body: io.NopCloser(strings.NewReader(`{}`)), Header: http.Header{}}, nil
	}
}
