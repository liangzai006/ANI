package objectstore

import (
	"context"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/kubercloud/ani/pkg/ports"
)

func TestMinIOObjectStoreEnsureBucketCreatesMissingBucketWithSignedRequest(t *testing.T) {
	t.Parallel()

	var requests []string
	client := &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		requests = append(requests, r.Method+" "+r.URL.Path)
		if !strings.HasPrefix(r.Header.Get("Authorization"), "AWS4-HMAC-SHA256") {
			t.Fatalf("request missing SigV4 authorization header: %q", r.Header.Get("Authorization"))
		}
		if r.Method == http.MethodHead {
			return minIOTestResponse(http.StatusNotFound), nil
		}
		return minIOTestResponse(http.StatusOK), nil
	})}

	store, err := NewMinIOObjectStore(MinIOObjectStoreConfig{
		Endpoint:        "http://minio.test",
		AccessKeyID:     "minio",
		SecretAccessKey: "secret",
		Region:          "us-east-1",
		HTTPClient:      client,
		Now:             fixedMinIOTestClock,
	})
	if err != nil {
		t.Fatalf("NewMinIOObjectStore() error = %v", err)
	}

	if err := store.EnsureBucket(context.Background(), ports.BucketClass("models-a")); err != nil {
		t.Fatalf("EnsureBucket() error = %v", err)
	}

	want := []string{"HEAD /models-a", "PUT /models-a"}
	if strings.Join(requests, ",") != strings.Join(want, ",") {
		t.Fatalf("requests = %v, want %v", requests, want)
	}
}

func TestMinIOObjectStoreEnsureBucketTreatsExistingBucketAsReady(t *testing.T) {
	t.Parallel()

	var putCalled bool
	client := &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		if r.Method == http.MethodPut {
			putCalled = true
		}
		return minIOTestResponse(http.StatusOK), nil
	})}

	store, err := NewMinIOObjectStore(MinIOObjectStoreConfig{
		Endpoint:        "http://minio.test",
		AccessKeyID:     "minio",
		SecretAccessKey: "secret",
		Region:          "us-east-1",
		HTTPClient:      client,
		Now:             fixedMinIOTestClock,
	})
	if err != nil {
		t.Fatalf("NewMinIOObjectStore() error = %v", err)
	}

	if err := store.EnsureBucket(context.Background(), ports.BucketClass("datasets-a")); err != nil {
		t.Fatalf("EnsureBucket() error = %v", err)
	}
	if putCalled {
		t.Fatal("EnsureBucket() called PUT after HEAD returned ready")
	}
}

func TestMinIOObjectStoreBuildsTenantScopedSignedUploadAndDownloadURLs(t *testing.T) {
	t.Parallel()

	store, err := NewMinIOObjectStore(MinIOObjectStoreConfig{
		Endpoint:        "https://minio.example:9000",
		AccessKeyID:     "minio",
		SecretAccessKey: "secret",
		SessionToken:    "session-token",
		Region:          "us-east-1",
		Now:             fixedMinIOTestClock,
	})
	if err != nil {
		t.Fatalf("NewMinIOObjectStore() error = %v", err)
	}
	ref := ports.ObjectRef{
		TenantID:    "tenant-a",
		BucketClass: ports.BucketClass("models-a"),
		ObjectKey:   "llm/model.bin",
	}

	upload, err := store.SignedUploadURL(context.Background(), ref, 10*time.Minute)
	if err != nil {
		t.Fatalf("SignedUploadURL() error = %v", err)
	}
	download, err := store.SignedDownloadURL(context.Background(), ref, 15*time.Minute)
	if err != nil {
		t.Fatalf("SignedDownloadURL() error = %v", err)
	}

	assertSignedURL(t, upload.URL, "https://minio.example:9000/models-a/tenant-a/llm/model.bin", "600")
	assertSignedURL(t, download.URL, "https://minio.example:9000/models-a/tenant-a/llm/model.bin", "900")
	if !upload.ExpiresAt.Equal(fixedMinIOTestClock().Add(10 * time.Minute)) {
		t.Fatalf("upload expires_at = %s", upload.ExpiresAt)
	}
	if !download.ExpiresAt.Equal(fixedMinIOTestClock().Add(15 * time.Minute)) {
		t.Fatalf("download expires_at = %s", download.ExpiresAt)
	}
}

func TestMinIOObjectStoreRejectsInvalidPresignInput(t *testing.T) {
	t.Parallel()

	store, err := NewMinIOObjectStore(MinIOObjectStoreConfig{
		Endpoint:        "http://minio.example:9000",
		AccessKeyID:     "minio",
		SecretAccessKey: "secret",
		Region:          "us-east-1",
		Now:             fixedMinIOTestClock,
	})
	if err != nil {
		t.Fatalf("NewMinIOObjectStore() error = %v", err)
	}

	_, err = store.SignedUploadURL(context.Background(), ports.ObjectRef{
		TenantID:    "tenant-a",
		BucketClass: ports.BucketClass("models-a"),
	}, time.Minute)
	if err == nil {
		t.Fatal("SignedUploadURL() error = nil, want invalid request error")
	}
}

func assertSignedURL(t *testing.T, rawURL string, wantPrefix string, wantExpires string) {
	t.Helper()

	if !strings.HasPrefix(rawURL, wantPrefix+"?") {
		t.Fatalf("signed URL = %q, want prefix %q", rawURL, wantPrefix+"?")
	}
	for _, token := range []string{
		"X-Amz-Algorithm=AWS4-HMAC-SHA256",
		"X-Amz-Credential=minio%2F20260619%2Fus-east-1%2Fs3%2Faws4_request",
		"X-Amz-Date=20260619T010203Z",
		"X-Amz-Security-Token=session-token",
		"X-Amz-SignedHeaders=host",
		"X-Amz-Signature=",
		"X-Amz-Expires=" + wantExpires,
	} {
		if !strings.Contains(rawURL, token) {
			t.Fatalf("signed URL %q missing %q", rawURL, token)
		}
	}
}

func fixedMinIOTestClock() time.Time {
	return time.Date(2026, 6, 19, 1, 2, 3, 0, time.UTC)
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) {
	return f(r)
}

func minIOTestResponse(statusCode int) *http.Response {
	return &http.Response{
		StatusCode: statusCode,
		Header:     http.Header{},
		Body:       io.NopCloser(strings.NewReader("")),
	}
}
