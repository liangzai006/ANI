# GATEWAY-METADATA-PERSISTENCE-P4

> 记录类型：Feature batch / Core Gateway metadata persistence follow-up
> 完成日期：2026-06-30
> 范围：Docker init 对齐 migration 015/016 + `PUT /branding` 写 PG

## 目标

1. 新 `make deps` 空卷自动具备 P1/P3 元数据表，无需手动跑 migration 015/016。
2. `PUT /api/v1/branding` 从 stub 改为经 `MetadataBrandingService` 更新 `platform_branding`（`DATABASE_URL` 未配置时 `LocalBrandingService` 进程内覆盖）。

## 实现

- 整合 Gateway 元数据 DDL 为 `deploy/postgres/gateway-metadata-schema.sql`（幂等，合并 migration 014–016）。
- `deploy/postgres/ani-dev-database-init.sql` 为开发完整初始化入口（含 auth + Core runtime + Gateway 元数据）；`make deps` 空卷自动执行。
- 已有 PG 卷：`make db-upgrade-gateway-metadata`。
- `PUT /branding` 写 `platform_branding`（见上文 P4 代码变更）。

## 真实 PostgreSQL 冒烟（2026-06-30）

| 场景 | 结果 |
|------|------|
| `GET /api/v1/branding` | 200，seed `KuberCloud ANI` |
| `PUT /api/v1/branding` | 200，`platform_branding` 行已更新 |
| 再次 `GET /api/v1/branding` | 200，与 PUT 响应一致 |

**PASS**

## 边界

- 不改 Core OpenAPI（`PUT /branding` 仍无契约 requestBody 定义，按 GET 响应字段子集接受 JSON）。
- `POST /branding/logo` 仍为 stub（返回当前 logo URL，不上传对象）。
- 已有 PG 数据卷不会自动重跑 init；执行 `make db-upgrade-gateway-metadata` 或 `deploy/postgres/gateway-metadata-schema.sql`。
- 不标 production ready。

## 验证

```bash
cd repo
make validate-gateway-metadata-p1
make validate-gateway-metadata
```

结果：gate 通过；PUT branding PG 冒烟 PASS。
