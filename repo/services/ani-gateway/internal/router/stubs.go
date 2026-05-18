// Package router contains stub route registrations.
// Each stub registers the correct URL structure and returns 501 Not Implemented.
// Replace each stub with the real handler as the service is built out.
package router

import (
	"context"
	"net/http"

	"github.com/cloudwego/hertz/pkg/app"
	"github.com/cloudwego/hertz/pkg/route"
	"github.com/kubercloud/ani/services/ani-gateway/internal/middleware"
)

func notImplemented(ctx context.Context, c *app.RequestContext) {
	c.JSON(http.StatusNotImplemented, map[string]any{
		"code":       "NOT_IMPLEMENTED",
		"message":    "this endpoint is not yet implemented",
		"request_id": middleware.GetRequestID(c),
	})
	_ = ctx
}

// ── Branding ──────────────────────────────────────────────────────────────────

func registerBranding(v1 *route.RouterGroup) {
	v1.GET("/branding", notImplemented)
	v1.PUT("/branding", notImplemented)
	v1.POST("/branding/logo", notImplemented)
}

// ── Models ────────────────────────────────────────────────────────────────────

func registerModels(v1 *route.RouterGroup) {
	v1.GET("/models", notImplemented)
	v1.POST("/models", notImplemented)
	v1.POST("/models/import", notImplemented)
	v1.GET("/models/:model_id", notImplemented)
	v1.DELETE("/models/:model_id", notImplemented)
	v1.GET("/models/:model_id/versions", notImplemented)
	v1.POST("/models/:model_id/versions", notImplemented)
}

// ── Inference Services ────────────────────────────────────────────────────────

func registerInferenceServices(v1 *route.RouterGroup) {
	v1.GET("/inference-services", notImplemented)
	v1.POST("/inference-services", notImplemented)
	v1.GET("/inference-services/:service_id", notImplemented)
	v1.PATCH("/inference-services/:service_id", notImplemented)
	v1.DELETE("/inference-services/:service_id", notImplemented)
	v1.GET("/inference-services/:service_id/logs", notImplemented)
}

// ── Knowledge Bases ───────────────────────────────────────────────────────────

func registerKnowledgeBases(v1 *route.RouterGroup) {
	v1.GET("/knowledge-bases", notImplemented)
	v1.POST("/knowledge-bases", notImplemented)
	v1.GET("/knowledge-bases/:kb_id", notImplemented)
	v1.DELETE("/knowledge-bases/:kb_id", notImplemented)
	v1.GET("/knowledge-bases/:kb_id/documents", notImplemented)
	v1.POST("/knowledge-bases/:kb_id/documents", notImplemented)
	v1.DELETE("/knowledge-bases/:kb_id/documents/:doc_id", notImplemented)
	v1.POST("/knowledge-bases/:kb_id/query", notImplemented)
	// SSE streaming query (separate endpoint from JSON to allow clean SDK generation)
	v1.GET("/knowledge-bases/:kb_id/query/stream", notImplemented)
}

// ── Tasks ─────────────────────────────────────────────────────────────────────

func registerTasks(v1 *route.RouterGroup) {
	v1.GET("/tasks/:task_id", notImplemented)
	v1.DELETE("/tasks/:task_id", notImplemented) // cancel
}

// ── Metering ──────────────────────────────────────────────────────────────────

func registerMetering(v1 *route.RouterGroup) {
	v1.GET("/metering/usage", notImplemented)
	v1.GET("/metering/summary", notImplemented)
}

// ── Harbor Proxy ──────────────────────────────────────────────────────────────

func registerHarbor(v1 *route.RouterGroup) {
	// Proxy requests to Harbor API; harbor-proxy module will forward with auth header
	v1.GET("/registry/projects", notImplemented)
	v1.GET("/registry/projects/:project/repositories", notImplemented)
	v1.GET("/registry/projects/:project/repositories/:repo/artifacts", notImplemented)
}

// ── OpenAI-Compatible Inference Proxy ─────────────────────────────────────────

// inferenceProxy routes /v1/chat/completions to the correct vLLM service
// based on X-Model-Name header, then streams the response back via SSE.
func inferenceProxy(ctx context.Context, c *app.RequestContext) {
	// TODO: read X-Model-Name header → lookup endpoint_url in Redis/DB
	// → reverse-proxy to vLLM with SSE streaming
	notImplemented(ctx, c)
}
