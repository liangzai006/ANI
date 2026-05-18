# M1-HEALTH-A — 健康检查端点

完成日期：2026-05-18
对应 Sprint：Sprint 1（2026-05-15 ~ 05-31）
验证结果：make build EXIT:0；make test EXIT:0；make validate-architecture passed；Gateway `/healthz` 与 `/readyz` smoke test passed

## 实现了什么

为 Gateway 和三个 gRPC 服务补齐标准健康检查能力。Gateway 在同一 HTTP 服务暴露 `/healthz` 和 `/readyz`；Auth/Model/Task 通过 `pkg/bootstrap` 随 gRPC 服务启动独立 HTTP probe server，`/readyz` 检查 Postgres、NATS、Redis 依赖状态。

## 关键文件改动

| 文件 | 新增/修改 | 说明 |
|---|---|---|
| `pkg/bootstrap/probes.go` | 新增 | 通用 liveness/readiness HTTP probe handler 与依赖检查 |
| `pkg/bootstrap/server.go` | 修改 | gRPC 服务启动时同步启动健康检查 HTTP server |
| `pkg/bootstrap/deps.go` | 修改 | Deps 记录 service name 和 health port |
| `services/ani-gateway/internal/router/health.go` | 修改 | Gateway 新增 `/healthz`、`/readyz`，保留 `/health`、`/ready` 兼容别名 |
| `services/ani-gateway/internal/middleware/auth.go` | 修改 | 将 `/healthz`、`/readyz` 加入免认证路径 |
| `services/auth-service/internal/config/config.go` | 修改 | Auth 默认 health port：9201 |
| `services/model-service/internal/config/config.go` | 修改 | Model 默认 gRPC port 修正为 9103，health port：9203 |
| `services/task-service/internal/config/config.go` | 修改 | Task 默认 health port：9204 |
| `pkg/bootstrap/probes_test.go` | 新增 | 覆盖 liveness 与 degraded readiness |
| `services/ani-gateway/internal/router/health_test.go` | 新增 | 覆盖 Gateway health response |

## 完工标准达成

- [x] `make build` 全通
- [x] `make test` 全通
- [x] `make validate-architecture` 通过
- [x] Gateway `/healthz` 返回 `{"status":"ok","version":"v0.8.0"}`
- [x] Gateway `/readyz` 返回 `{"status":"ok","checks":{...}}`
- [x] Auth/Model/Task 通过 bootstrap 具备 `/healthz` 与 `/readyz` HTTP probe server

## 备注

Auth/Model/Task 的 `/readyz` 依赖真实 Postgres、NATS、Redis 连接，当前单测覆盖 handler 与失败降级逻辑；完整 curl 验收需要 `make deps` 后分别访问 9201、9203、9204。
