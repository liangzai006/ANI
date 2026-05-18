package bootstrap

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestProbeHandlerHealthz(t *testing.T) {
	handler := newProbeHandler("test-service", nil)
	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/healthz", nil))

	if recorder.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", recorder.Code)
	}
	var body probeResponse
	if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Status != "ok" || body.Version == "" {
		t.Fatalf("body = %+v, want ok with version", body)
	}
}

func TestRunProbeChecksDegradesOnDependencyFailure(t *testing.T) {
	result := runProbeChecks(context.Background(), []probeCheck{
		{name: "postgres", run: func(context.Context) error { return nil }},
		{name: "redis", run: func(context.Context) error { return errors.New("dial failed") }},
	})

	if result.Status != "degraded" {
		t.Fatalf("status = %q, want degraded", result.Status)
	}
	if result.Checks["postgres"].Status != "ok" {
		t.Fatalf("postgres status = %q, want ok", result.Checks["postgres"].Status)
	}
	if result.Checks["redis"].Status != "fail" || result.Checks["redis"].Error == "" {
		t.Fatalf("redis check = %+v, want fail with error", result.Checks["redis"])
	}
}
