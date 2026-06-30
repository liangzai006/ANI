# GATEWAY-METADATA-PERSISTENCE-P5

> 记录类型：Feature batch / Core Gateway metadata persistence
> 完成日期：2026-06-30
> 范围：ANI Core / ani-gateway 镜像仓库（Registry）元数据 PostgreSQL 持久化（local + Harbor）

## 目标

`DATABASE_URL` 启用时，Registry 项目 / 仓库权限 / pull secret 元数据 write-through 并读 PG；Gateway 重启后可恢复项目列表。Harbor provider 在调真实 Harbor API 成功后同样 upsert PG（`provider_mode=harbor`），PG 作为 ANI 侧元数据索引，Harbor 仍为 artifacts/repositories 真源。

## 实现

- Migration `20260629_017_gateway_metadata_p5.sql`：`registry_projects`、`registry_repository_permissions`、`registry_pull_secrets`（不存密钥明文）及 RLS。
- 新增 `ports.RegistryResourceStore` 与 `pkg/adapters/runtime/registry_store.go`（`MetadataRegistryStore`）。
- 新增 `pkg/adapters/registry/persisting_image_registry.go`：`PersistingImageRegistry` 装饰 local/Harbor `ImageRegistry`。
- `newGatewayImageRegistry(cfg, metadataStore)`：`DATABASE_URL` 时 local 不再走 router 内存 fallback，而是 PG 包装；Harbor 同样包装。
- 同步 `deploy/postgres/gateway-metadata-schema.sql`、`deploy/real-k8s-lab/auth-dex-production-db-init.sql`。
- 新增 `make validate-gateway-metadata-p5`；聚合 gate 扩展为 P0–P5。

## 覆盖范围

| 资源 | Create/Upsert PG | List/Get 读 PG |
|------|------------------|----------------|
| RegistryProject | ✅（local + harbor） | ✅ ListProjects 读 PG |
| RegistryRepositoryPermission | ✅ | 幂等重放读 PG；ListRepositories 可从 PG 补全 permission |
| RegistryPullSecret（元数据） | ✅ | 幂等重放读 PG |

不持久化：repositories / artifacts / scan 结果（仍走 provider 实时 API）。

## 真实 PostgreSQL 冒烟（2026-06-30）

环境：`ani-postgres`、`DATABASE_URL=postgres://ani:ani_dev_password@127.0.0.1:5432/ani?sslmode=disable`、`ANI_AUTH_MODE=dev`、`GATEWAY_HTTP_ADDR=:18080`。

| 场景 | 结果 |
|------|------|
| `POST /api/v1/registry/projects` → `registry_projects` 有行 | PASS |
| 重启 Gateway → `GET /api/v1/registry/projects` 仍含项目 | PASS |

**PASS**

## 边界

- 不改 Core OpenAPI；不声明 real-provider / production ready。
- `DATABASE_URL` 未设置时保持原行为（router 内存 local profile；Harbor 无 PG 包装）。
- Redis 仍只做幂等/限流。
- Harbor live gate（`SPRINT13-REGISTRY-HARBOR-A`）仍独立，本批次不替代真实 Harbor 验收。

## 验证

```bash
cd repo
make validate-gateway-metadata-p5
make validate-gateway-metadata
go test ./pkg/adapters/runtime/... ./pkg/adapters/registry/... ./services/ani-gateway/... -count=1
```

## 系列状态

P0–P5 Gateway 元数据持久化主线已闭合（实例/网络/存储/branding/tasks/metering/vector/registry 控制面元数据）。后续 backlog 见 CURRENT-SPRINT「Gateway 元数据剩余项」。
