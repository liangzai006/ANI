package middleware

import (
	"context"
	"net/http"
	"os"
	"strings"

	"github.com/cloudwego/hertz/pkg/app"
)

// Auth validates JWT Bearer tokens or API Keys.
// On success it sets "tenant_id" and "user_id" in the request context.
// This is fail-closed by default. Local development may set ANI_AUTH_MODE=dev
// and pass X-Dev-Tenant-ID to exercise routes before auth-service exists.
func Auth() app.HandlerFunc {
	return AuthWithClient(NewAuthClientFromEnv())
}

func AuthWithClient(authClient AuthClient) app.HandlerFunc {
	return func(ctx context.Context, c *app.RequestContext) {
		if isPublicPath(string(c.Path())) {
			c.Next(ctx)
			return
		}

		if os.Getenv("ANI_AUTH_MODE") == "dev" {
			tenantID := string(c.GetHeader("X-Dev-Tenant-ID"))
			if tenantID == "" {
				tenantID = "00000000-0000-0000-0000-000000000001"
			}
			userID := string(c.GetHeader("X-Dev-User-ID"))
			if userID == "" {
				userID = "00000000-0000-0000-0000-000000000001"
			}
			c.Set("tenant_id", tenantID)
			c.Set("user_id", userID)
			c.Set("roles", []string{"tenant-admin"})
			c.Next(ctx)
			return
		}

		// 1. Try Bearer token
		authHeader := string(c.GetHeader("Authorization"))
		if strings.HasPrefix(authHeader, "Bearer ") {
			token := strings.TrimPrefix(authHeader, "Bearer ")
			if authClient == nil {
				respondError(c, http.StatusUnauthorized, "UNAUTHORIZED", "auth service unavailable")
				return
			}
			tenantCtx, err := authClient.ValidateToken(ctx, token)
			if err != nil {
				respondError(c, http.StatusUnauthorized, "UNAUTHORIZED", "invalid or expired token")
				return
			}
			setTenantContext(c, tenantCtx.GetTenantId(), tenantCtx.GetUserId(), tenantCtx.GetRoles())
			c.Next(ctx)
			return
		}

		// 2. Try API Key
		apiKey := string(c.GetHeader("X-API-Key"))
		if apiKey != "" {
			if authClient == nil {
				respondError(c, http.StatusUnauthorized, "UNAUTHORIZED", "auth service unavailable")
				return
			}
			tenantCtx, err := authClient.ValidateToken(ctx, apiKey)
			if err != nil {
				respondError(c, http.StatusUnauthorized, "UNAUTHORIZED", "invalid api key")
				return
			}
			setTenantContext(c, tenantCtx.GetTenantId(), tenantCtx.GetUserId(), tenantCtx.GetRoles())
			c.Next(ctx)
			return
		}

		respondError(c, http.StatusUnauthorized, "UNAUTHORIZED", "authentication required")
	}
}

func setTenantContext(c *app.RequestContext, tenantID, userID string, roles []string) {
	c.Set("tenant_id", tenantID)
	c.Set("user_id", userID)
	c.Set("roles", roles)
}

func isPublicPath(path string) bool {
	switch path {
	case "/health", "/ready", "/healthz", "/readyz", "/api/v1/branding", "/api/v1/auth/oidc/begin", "/api/v1/auth/token", "/api/v1/auth/refresh":
		return true
	default:
		return false
	}
}
