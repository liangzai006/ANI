package router

import (
	"context"
	"net/http"

	"github.com/cloudwego/hertz/pkg/app"
	"github.com/cloudwego/hertz/pkg/route"
)

const healthVersion = "v0.8.0"

type healthResponse struct {
	Status  string                 `json:"status"`
	Version string                 `json:"version,omitempty"`
	Checks  map[string]healthCheck `json:"checks,omitempty"`
}

type healthCheck struct {
	Status    string `json:"status"`
	LatencyMS int64  `json:"latency_ms"`
	Error     string `json:"error,omitempty"`
}

func registerHealth(r *route.RouterGroup) {
	r.GET("/healthz", func(ctx context.Context, c *app.RequestContext) {
		c.JSON(http.StatusOK, livenessResponse())
	})
	r.GET("/readyz", func(ctx context.Context, c *app.RequestContext) {
		c.JSON(http.StatusOK, readinessResponse())
	})
	r.GET("/health", func(ctx context.Context, c *app.RequestContext) {
		c.JSON(http.StatusOK, livenessResponse())
	})
	r.GET("/ready", func(ctx context.Context, c *app.RequestContext) {
		c.JSON(http.StatusOK, readinessResponse())
	})
}

func livenessResponse() healthResponse {
	return healthResponse{
		Status:  "ok",
		Version: healthVersion,
	}
}

func readinessResponse() healthResponse {
	return healthResponse{
		Status: "ok",
		Checks: map[string]healthCheck{
			"process": {
				Status:    "ok",
				LatencyMS: 0,
			},
		},
	}
}
