# GATEWAY-METADATA-PERSISTENCE-P6-A2

> 记录类型：Feature batch / Core Gateway metadata persistence（阶段 A · A2）
> 完成日期：2026-06-30
> 范围：ANI Core / ani-gateway Secret 元数据与绑定记录 PostgreSQL 持久化（无明文）

## 目标

`DATABASE_URL` 启用时，Secret 元数据（name/type/keys 名称列表/state/provider refs）与 binding 记录 write-through 并 List/Get 读 PG；**永不**将 `data` 明文写入 PostgreSQL。Gateway 重启后可恢复 Secret 列表与元数据查询；local profile 明文仍仅存进程内存（与 OpenAPI 语义一致）。

## 实现

- Migration `20260630_019_gateway_metadata_p6_a2.sql`：`secrets`、`secret_bindings` 及 RLS。
- 新增 `ports.SecretResourceStore` 与 `pkg/adapters/runtime/secret_store.go`（`MetadataSecretStore`）。
- `localSecretService` 增加 `WithSecretResourceStore`：Create/Delete/Bind 写 PG；List 读 PG；Get 内存优先 → PG。
- `newGatewaySecretService(cfg, metadataStore)`：`DATABASE_URL` 时 local profile 注入 PG store；`kubernetes_rest` 同样在元数据层写 PG。
- 同步 `deploy/postgres/gateway-metadata-schema.sql` 与 dev init 脚本。
- 新增 `make validate-gateway-metadata-p6-a2`；聚合 gate 扩展含 P6-A2。

## 覆盖范围

| 资源 | Create/Upsert PG | List/Get 读 PG | 明文 |
|------|------------------|----------------|------|
| Secret 元数据 | ✅ | ✅ | ❌ 不落 PG |
| SecretBinding | ✅ | — | — |

不持久化：Secret `data` 明文、K8s Secret 注入执行结果（仍走 provider/controller 边界）。

## 验收

```bash
cd repo
make validate-gateway-metadata-p6-a2
make validate-gateway-metadata
```

## 边界

- `DATABASE_URL` 未设：保持内存模式（router fallback）。
- 重启后 List/Get 元数据可恢复；明文需重新 Create 或走 real K8s provider。
- 不标 real-provider / production ready。
