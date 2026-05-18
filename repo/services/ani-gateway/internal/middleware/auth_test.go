package middleware

import "testing"

func TestAuthPublicPaths(t *testing.T) {
	publicPaths := []string{
		"/health",
		"/ready",
		"/healthz",
		"/readyz",
		"/api/v1/branding",
		"/api/v1/auth/oidc/begin",
		"/api/v1/auth/token",
		"/api/v1/auth/refresh",
	}
	for _, path := range publicPaths {
		if !isPublicPath(path) {
			t.Fatalf("isPublicPath(%q) = false, want true", path)
		}
	}
}

func TestAuthProtectedPaths(t *testing.T) {
	protectedPaths := []string{
		"/api/v1/auth/logout",
		"/api/v1/auth/api-keys",
		"/api/v1/instances",
	}
	for _, path := range protectedPaths {
		if isPublicPath(path) {
			t.Fatalf("isPublicPath(%q) = true, want false", path)
		}
	}
}
