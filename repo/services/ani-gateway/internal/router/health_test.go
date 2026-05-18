package router

import "testing"

func TestLivenessResponse(t *testing.T) {
	response := livenessResponse()
	if response.Status != "ok" || response.Version == "" {
		t.Fatalf("liveness response = %+v, want ok with version", response)
	}
}

func TestReadinessResponse(t *testing.T) {
	response := readinessResponse()
	if response.Status != "ok" {
		t.Fatalf("readiness status = %q, want ok", response.Status)
	}
	if response.Checks["process"].Status != "ok" {
		t.Fatalf("process check = %+v, want ok", response.Checks["process"])
	}
}
