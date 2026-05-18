package middleware

import (
	"context"

	"github.com/cloudwego/hertz/pkg/app"
	"github.com/cloudwego/hertz/pkg/common/utils"
	"github.com/google/uuid"
)

const keyRequestID = "request_id"

// RequestID injects a unique request ID into every request context and response header.
func RequestID() app.HandlerFunc {
	return func(ctx context.Context, c *app.RequestContext) {
		reqID := string(c.GetHeader("X-Request-ID"))
		if reqID == "" {
			reqID = "req_" + uuid.New().String()
		}
		c.Set(keyRequestID, reqID)
		c.Header("X-Request-ID", reqID)
		c.Next(ctx)
	}
}

// GetRequestID retrieves the request ID from context.
func GetRequestID(c *app.RequestContext) string {
	v, _ := c.Get(keyRequestID)
	if id, ok := v.(string); ok {
		return id
	}
	return ""
}

// GetTenantID retrieves the tenant ID set by the Auth middleware.
func GetTenantID(c *app.RequestContext) string {
	v, _ := c.Get("tenant_id")
	if id, ok := v.(string); ok {
		return id
	}
	return ""
}

// GetUserID retrieves the user ID set by the Auth middleware.
func GetUserID(c *app.RequestContext) string {
	v, _ := c.Get("user_id")
	if id, ok := v.(string); ok {
		return id
	}
	return ""
}

// respondError writes a standardized ANI error response.
func respondError(c *app.RequestContext, statusCode int, code, message string) {
	c.JSON(statusCode, utils.H{
		"code":       code,
		"message":    message,
		"request_id": GetRequestID(c),
	})
	c.Abort()
}
