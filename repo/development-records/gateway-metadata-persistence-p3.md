# GATEWAY-METADATA-PERSISTENCE-P3

> 记录类型：Feature batch / Core Gateway metadata persistence
> 完成日期：2026-06-29
> 范围：ANI Core / ani-gateway 存储扩展元数据 PostgreSQL 持久化（bucket / volume snapshot / mount target）

## 目标

补齐 P2 未覆盖的存储元数据：`StorageBucket`、`VolumeSnapshot`、`FilesystemMountTarget` 在 `DATABASE_URL` 启用时 write-through 并读 PG，Gateway 重启后可恢复。

## 实现

- Migration `20260629_016_gateway_metadata_p3.sql`：新增 `storage_buckets`、`volume_snapshots`、`filesystem_mount_targets` 表及 RLS。
- 扩展 `ports.StorageResourceStore`：Upsert/List/Get 上述三类资源；bucket 幂等键与按名查重。
- 新增 `pkg/adapters/runtime/storage_store_p3.go`：metadata adapter 读写实现。
- 修改 `LocalStorageService`：
  - `CreateStorageBucket` / `ListStorageBuckets` 有 store 时走 PG；
  - `CreateVolumeSnapshot` / `ListVolumeSnapshots` 有 store 时走 PG；
  - `ListFilesystemMountTargets` 优先读 PG，缺失时懒创建并 upsert；
  - `CreateStorageObjectUpload` 通过 `lookupBucket` 校验父 bucket。
- 增强测试 fake `Query` / `QueryRow` 序列支持。
- 新增 `make validate-gateway-metadata-p3`。

## 覆盖范围

| 资源 | Create/Upsert PG | List/Get 读 PG |
|------|------------------|----------------|
| StorageBucket | ✅ | ✅ |
| VolumeSnapshot | ✅ | ✅（按 volume_id） |
| FilesystemMountTarget | ✅（懒创建） | ✅（按 filesystem_id） |

## 真实 PostgreSQL 冒烟（2026-06-30）

环境：`ani-postgres` docker、`DATABASE_URL=postgres://ani:ani_dev_password@127.0.0.1:5432/ani?sslmode=disable`、`ANI_AUTH_MODE=dev`、`GATEWAY_HTTP_ADDR=:18080`。

| 场景 | 结果 |
|------|------|
| `POST /api/v1/buckets` → 重启 Gateway → `GET /api/v1/buckets` | 200，`storage_buckets` 有行，列表含 `p3-bucket-*` |
| `POST /api/v1/volumes` + `POST .../snapshots` → 重启 → `GET .../snapshots` | 200，`volume_snapshots` 有行 |
| `POST /api/v1/filesystems` + `GET .../mount-targets` → 重启 → 同上 | 200，`filesystem_mount_targets` 有行 |

**PASS**

## 边界

- 不改 Core OpenAPI；不声明 real-provider / production ready。
- `DATABASE_URL` 未设置时保持内存模式（向后兼容）。
- Redis 仍只做幂等/限流，不承载业务元数据。

## 验证

```bash
cd repo
make validate-gateway-metadata-p3
make validate-gateway-metadata-p2
go test ./pkg/adapters/runtime/... ./services/ani-gateway/... -count=1
```

结果：上述 gate 与单元测试通过；真实 PG 冒烟 PASS。

## 系列闭环

P0–P3 全部完成；聚合验收：

```bash
cd repo
make validate-gateway-metadata
```

顺序执行 `validate-gateway-metadata-p0` … `p3`；Sprint 14 resilience 回归入口已引用该聚合 gate。
