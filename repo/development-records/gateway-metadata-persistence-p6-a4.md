# GATEWAY-METADATA-PERSISTENCE-P6-A4

> 记录类型：Feature batch / Core Gateway metadata persistence（阶段 A · A4）
> 完成日期：2026-06-30
> 范围：ANI Core / Encryption key 元数据 PostgreSQL 持久化（无 key material / seal token）

## 目标

`DATABASE_URL` 启用时，encryption key 元数据（name/algorithm/state/provider refs）write-through 并 List/Get 读 PG；**永不**将 key material、seal/unseal token 写入 PostgreSQL。Gateway 重启后可恢复 key 列表与元数据查询。

## 实现

- Migration `20260630_020_gateway_metadata_p6_a4.sql`：`encryption_keys` 及 RLS。
- 新增 `ports.EncryptionKeyResourceStore` 与 `pkg/adapters/runtime/encryption_key_store.go`（`MetadataEncryptionKeyStore`）。
- `localEncryptionService` 增加 `WithEncryptionResourceStore`：Create/Delete/Rotate/Revoke 写 PG；List 读 PG；Get 内存优先 → PG。
- `newGatewayEncryptionService(cfg, metadataStore)`：`DATABASE_URL` 时 local profile 注入 PG store；`kms_sm4_http` 同样在元数据层写 PG。
- 同步 `deploy/postgres/gateway-metadata-schema.sql` 与 dev init 脚本。
- 新增 `make validate-gateway-metadata-p6-a4`；聚合 gate 扩展含 P6-A4。

## 覆盖范围

| 资源 | Create/Upsert PG | List/Get 读 PG | key material / seal token |
|------|------------------|----------------|---------------------------|
| EncryptionKey 元数据 | ✅ | ✅ | ❌ 不落 PG |

## 验收

```bash
cd repo
make validate-gateway-metadata-p6-a4
make validate-gateway-metadata
```

## 边界

- `DATABASE_URL` 未设：保持内存模式。
- Seal/unseal 记录与 token 仍仅存进程内存（与 OpenAPI 语义一致）。
- 不标 real-provider / production ready。
