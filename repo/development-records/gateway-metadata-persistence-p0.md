# GATEWAY-METADATA-PERSISTENCE-P0

> 记录类型：Feature batch / Core Gateway metadata persistence
> 完成日期：2026-06-29
> 范围：ANI Core / ani-gateway PostgreSQL 元数据持久化 P0

## 目标

将 ani-gateway 中实例、网络、存储等 Core local profile 元数据从进程内内存 map 切换到 PostgreSQL，复用既有 `ports.MetadataStore` 与 `pkg/adapters/runtime` metadata adapter；`DATABASE_URL` 未配置时保持原有内存行为，Redis 继续仅承担幂等/限流缓存职责。

## 实现

- 新增 `services/ani-gateway/gateway_db_runtime.go`：
  - `connectGatewayMetadataStore()` 读取 `DATABASE_URL`，经 `bootstrap.ConnectMetadataStore` 构造共享 `ports.MetadataStore`。
- 修改 `services/ani-gateway/main.go`：
  - 启动时连接 metadata store 并注入 router、network/storage runtime、k8s cluster proxy（共享同一连接，避免重复建连）。
- 修改 `services/ani-gateway/internal/router/demo_instances.go` 与 `router.go`：
  - `RegisterOptions.MetadataStore` 存在时，实例/操作/Workload Identity/Plan Audit 走 `MetadataInstanceStore`、`MetadataOperationStore`、`MetadataWorkloadIdentityService`、`MetadataPlanAuditStore`。
- 修改 `services/ani-gateway/network_runtime.go`、`storage_runtime.go`：
  - 存在 metadata store 时，local profile 也注入 `MetadataNetworkStore` / `MetadataStorageStore`。
- 新增 migration `deploy/migrations/20260629_014_gateway_metadata_alignment.sql`：
  - `workload_instances` reconcile 扫描索引；
  - 修正 `network_routes` RLS 为 `app.current_tenant_id`（与 `types.SetDBTenant` 一致）。
- 新增 `make validate-gateway-metadata-p0` 与聚合 `make validate-gateway-metadata`（顺序执行 P0–P3 sub-gate）。
- 修改 `services/ani-gateway/internal/middleware/auth.go`：
  - Auth 成功后将 `types.TenantContext` 注入 `context.Context`，供 `SetDBTenant` / metadata store 使用。
- 新增 `GATEWAY_HTTP_ADDR` 环境变量（默认 `:8080`），便于本地多实例冒烟。

## 真实 PostgreSQL 冒烟（2026-06-29）

环境：`ani-postgres` docker、`DATABASE_URL=postgres://ani:ani_dev_password@127.0.0.1:5432/ani?sslmode=disable`、`ANI_AUTH_MODE=dev`。

```bash
export DATABASE_URL='postgres://ani:ani_dev_password@127.0.0.1:5432/ani?sslmode=disable'
export ANI_AUTH_MODE=dev
export GATEWAY_HTTP_ADDR=':18080'
export GATEWAY_REDIS_URL='redis://:ani_dev_password@127.0.0.1:6379/0'
go run ./services/ani-gateway
# POST /api/v1/instances → 重启 gateway → GET 同一 instance_id → 200
# docker exec ani-postgres psql ... SELECT FROM workload_instances 可见行
```

结果：创建 `inst_*` VM 实例 HTTP 201；Gateway 重启后 GET 200 且 `name` 一致；`workload_instances` 表有对应行。**PASS**。

| API 资源 | PostgreSQL 表 |
|---|---|
| `InstanceRecord` | `workload_instances` |
| `InstanceOperation` | `workload_instance_operations` + `workload_instance_operation_steps` |
| `WorkloadIdentityBinding` | `api_keys`（`instance_id`） |
| Network VPC/Subnet/SG/LB/Route | `network_vpcs` / `network_subnets` / `network_security_groups` / `network_load_balancers` / `network_routes` |
| Storage Volume/Filesystem/Object | `storage_volumes` / `storage_filesystems` / `storage_objects` |

## 边界

- 不改 Core OpenAPI，不改 Services OpenAPI，不新增 Services 逻辑。
- Redis（`GATEWAY_REDIS_URL` / `REDIS_URL`）仍只用于 gateway middleware 幂等重放与限流，不承载业务元数据。
- `DATABASE_URL` 未设置时行为与改前一致（内存 store）；不声明 real-provider / production ready。
- P1（branding、async_tasks、metering、vector_stores 元数据表）已在本批后续切片 `GATEWAY-METADATA-PERSISTENCE-P1` 完成；见 `gateway-metadata-persistence-p1.md`。

## 配置

```bash
# 启用 PostgreSQL 元数据持久化
export DATABASE_URL='postgres://ani:ani_dev_password@127.0.0.1:5432/ani?sslmode=disable'

# 首次或增量应用 migration（按顺序执行 deploy/migrations/*.sql）
psql "$DATABASE_URL" -f deploy/migrations/20260629_014_gateway_metadata_alignment.sql
```

本地 docker：`make deps` 空卷执行 `deploy/postgres/ani-dev-database-init.sql`（含 Gateway 元数据）；已有卷 `make db-upgrade-gateway-metadata`。详见 `deploy/postgres/README.md`。

## 验证

```bash
cd repo
make validate-gateway-metadata-p0
make validate-gateway-metadata   # 聚合 P0–P3
go test ./services/ani-gateway/... -count=1
go test ./services/ani-gateway/internal/router -run DemoInstance -count=1

# 可选：有 PostgreSQL 时持久化冒烟
# POST /api/v1/instances → 重启 gateway → GET 实例仍在
```

结果：`make validate-gateway-metadata` 与 `go test ./services/ani-gateway/...` 通过。
