package main

import (
	"context"
	"io"
	"net/http"
	"strings"
	"testing"

	"github.com/kubercloud/ani/pkg/ports"
)

func TestGatewayStorageServiceFromConfigDefaultsToRouterLocalService(t *testing.T) {
	service, err := newGatewayStorageService(gatewayStorageRuntimeConfig{})
	if err != nil {
		t.Fatalf("newGatewayStorageService() error = %v", err)
	}
	if service != nil {
		t.Fatalf("service = %T, want nil so router keeps local default", service)
	}
}

func TestGatewayStorageServiceFromConfigUsesKubernetesProvider(t *testing.T) {
	transport := &gatewayStorageRoundTripper{}
	service, err := newGatewayStorageService(gatewayStorageRuntimeConfig{
		ProviderMode:         "kubernetes_rest",
		ProviderApply:        true,
		ProviderUserID:       "ani-core-storage-provider",
		ProviderProof:        "rbac-scope:storage.write",
		KubernetesAPIHost:    "https://kubernetes.example.test",
		KubernetesHTTPClient: &http.Client{Transport: transport},
	})
	if err != nil {
		t.Fatalf("newGatewayStorageService() error = %v", err)
	}
	if service == nil {
		t.Fatalf("service = nil, want provider-backed storage service")
	}
	volume, err := service.CreateVolume(context.Background(), ports.StorageVolumeCreateRequest{
		TenantID:       "tenant-a",
		IdempotencyKey: "storage-volume-a",
		Name:           "data-a",
		SizeGiB:        1,
		StorageClass:   "ani-rbd-ssd",
	})
	if err != nil {
		t.Fatalf("CreateVolume() error = %v", err)
	}
	snapshot, err := service.CreateVolumeSnapshot(context.Background(), ports.VolumeSnapshotCreateRequest{
		TenantID:       "tenant-a",
		IdempotencyKey: "storage-snapshot-a",
		VolumeID:       volume.VolumeID,
		Name:           "data-a-snap",
	})
	if err != nil {
		t.Fatalf("CreateVolumeSnapshot() error = %v", err)
	}
	if snapshot.Status != ports.VolumeSnapshotAvailable {
		t.Fatalf("snapshot status = %s, want available from Kubernetes observe", snapshot.Status)
	}
	if transport.postCalls != 2 || transport.patchCalls != 2 || transport.getCalls != 2 {
		t.Fatalf("transport post=%d patch=%d get=%d, want volume and snapshot dry-run/apply/observe", transport.postCalls, transport.patchCalls, transport.getCalls)
	}
}

func TestGatewayStorageServiceRejectsKubernetesProviderWithoutProof(t *testing.T) {
	if _, err := newGatewayStorageService(gatewayStorageRuntimeConfig{
		ProviderMode:      "kubernetes_rest",
		KubernetesAPIHost: "https://kubernetes.example.test",
	}); err == nil {
		t.Fatalf("newGatewayStorageService() error = nil, want missing proof error")
	}
}

type gatewayStorageRoundTripper struct {
	postCalls  int
	patchCalls int
	getCalls   int
}

func (t *gatewayStorageRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	switch req.Method {
	case http.MethodPost:
		t.postCalls++
		return &http.Response{StatusCode: http.StatusOK, Body: io.NopCloser(strings.NewReader(`{"kind":"Accepted"}`)), Header: http.Header{}}, nil
	case http.MethodPatch:
		t.patchCalls++
		return &http.Response{StatusCode: http.StatusOK, Body: io.NopCloser(strings.NewReader(`{"kind":"Applied"}`)), Header: http.Header{}}, nil
	case http.MethodGet:
		t.getCalls++
		if strings.Contains(req.URL.Path, "/volumesnapshots/") {
			return &http.Response{
				StatusCode: http.StatusOK,
				Body:       io.NopCloser(strings.NewReader(`{"kind":"VolumeSnapshot","status":{"readyToUse":true}}`)),
				Header:     http.Header{},
			}, nil
		}
		return &http.Response{
			StatusCode: http.StatusOK,
			Body:       io.NopCloser(strings.NewReader(`{"kind":"PersistentVolumeClaim","status":{"phase":"Bound"}}`)),
			Header:     http.Header{},
		}, nil
	default:
		return &http.Response{StatusCode: http.StatusMethodNotAllowed, Body: io.NopCloser(strings.NewReader(`{}`)), Header: http.Header{}}, nil
	}
}
