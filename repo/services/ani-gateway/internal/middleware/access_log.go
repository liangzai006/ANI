package middleware

import (
	"context"
	"log/slog"
	"time"

	"github.com/cloudwego/hertz/pkg/app"
)

// AccessLog writes one structured log line per HTTP request to stdout.
func AccessLog() app.HandlerFunc {
	return func(ctx context.Context, c *app.RequestContext) {
		start := time.Now()
		c.Next(ctx)
		slog.Info("gateway http request",
			"method", string(c.Method()),
			"path", string(c.Path()),
			"query", string(c.QueryArgs().QueryString()),
			"status", c.Response.StatusCode(),
			"duration_ms", time.Since(start).Milliseconds(),
			"request_id", GetRequestID(c),
			"tenant_id", GetTenantID(c),
			"client_ip", c.ClientIP(),
		)
	}
}
