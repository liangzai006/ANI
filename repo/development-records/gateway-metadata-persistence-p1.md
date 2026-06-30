# GATEWAY-METADATA-PERSISTENCE-P1

> 记录类型：Feature batch / Core Gateway metadata persistence
> 完成日期：2026-06-29
> 范围：ANI Core / ani-gateway PostgreSQL 元数据持久化 P1

## 目标

在 P0 基础上，将 branding、async_tasks、metering、vector_stores 元数据从 Gateway stub/内存实现切换到 PostgreSQL；`DATABASE_URL` 未配置时保持原有 local profile 行为。

## 实现

- 新增 ports：`BrandingService`、`AsyncTaskService`、`VectorStoreMetadataStore`；扩展 `MeteringService` 已有 PG 适配。
- 新增 runtime adapters：
  - `MetadataBrandingService` / `LocalBrandingService`
  - `MetadataAsyncTaskService` / `LocalAsyncTaskService`
  - `MetadataMeteringService`（token 上报幂等 + `metering_records` 聚合）
  - `MetadataVectorStoreMetadataStore`
- 扩展 `LocalVectorStoreService`：`WithVectorStoreMetadataStore` 时 Create 写穿 PG，List/Get/Delete 以 PG 为准（重启可恢复元数据）。
- 修改 Gateway router：`branding_resources.go`、`task_resources.go`、`metering_resources.go` 注入 metadata 服务；`RegisterOptions` 增加 `BrandingService` / `AsyncTaskService` / `MeteringService`。
- 修改 `gateway_db_runtime.go`、`vector_store_runtime.go`、`main.go`：有 `DATABASE_URL` 时构造 P1 服务；无 Milvus provider 时也可仅 PG 持久化 vector store 元数据。
- 新增 migration `deploy/migrations/20260629_015_gateway_metadata_p1.sql`：
  - `vector_stores`（租户 RLS）
  - `metering_token_reports`（token 上报幂等，租户 RLS）
  - `metering_records`（`IF NOT EXISTS`，兼容 docker 局部 init 环境）
- 新增 `make validate-gateway-metadata-p1`。

## 真实 PostgreSQL 冒烟（2026-06-29）

环境：`ani-postgres` docker、`DATABASE_URL=postgres://ani:ani_dev_password@127.0.0.1:5432/ani?sslmode=disable`、`ANI_AUTH_MODE=dev`、`GATEWAY_HTTP_ADDR=:18080`。

| 场景 | 结果 |
|---|---|
| `GET /api/v1/branding` | 200，返回 `platform_branding` seed（`KuberCloud ANI`） |
| `POST /api/v1/metering/token-usage` | 202 accepted，写入 `metering_token_reports` + `metering_records` |
| `GET /api/v1/metering/usage` | 200，聚合 `token_input` / `token_output` / `token_total` |
| `GET /api/v1/tasks/{task_id}` | 200，读取 `async_tasks` 行 |
| `POST /api/v1/vector-stores` → 重启 Gateway → `GET` | 200，`vector_stores` 表有行，重启后仍可 GET |

**PASS**（重复 POST 同一 `idempotency_key` 时 Gateway HTTP 幂等中间件可能重放首次 202 响应，属预期）。

| API 资源 | PostgreSQL 表 |
|---|---|
| Platform branding | `platform_branding`（`WithPlatformTx`） |
| AsyncTask | `async_tasks` |
| Token usage report | `metering_token_reports` + `metering_records` |
| VectorStore 元数据 | `vector_stores`（Milvus 仍管向量数据） |

## 边界

- 不改 Core OpenAPI；`POST /branding/logo` 仍为 stub。`PUT /branding` 已在 `GATEWAY-METADATA-PERSISTENCE-P4` 接 PG，见 `gateway-metadata-persistence-p4.md`。
- `DELETE /tasks/{task_id}` 未在 OpenAPI 声明，实现为 PG cancel（`status=cancelled`）。
- 网络/存储 List/Get 读路径已在 `GATEWAY-METADATA-PERSISTENCE-P2` 完成；见 `gateway-metadata-persistence-p2.md`。
- 不声明 real-provider / production ready。

## 配置

```bash
export DATABASE_URL='postgres://ani:ani_dev_password@127.0.0.1:5432/ani?sslmode=disable'
psql "$DATABASE_URL" -f deploy/migrations/20260629_015_gateway_metadata_p1.sql
```

## 验证

```bash
cd repo
make validate-gateway-metadata-p1
make validate-gateway-metadata
go test ./services/ani-gateway/... -count=1
```

结果：上述 gate 与 gateway 测试通过；真实 PG 冒烟通过。
