# GATEWAY-METADATA-PERSISTENCE-P2

> 记录类型：Feature batch / Core Gateway metadata persistence
> 完成日期：2026-06-29
> 范围：ANI Core / ani-gateway 网络与存储元数据 PostgreSQL 读路径

## 目标

修复 P0/P1 已知局限：网络/存储资源在 `DATABASE_URL` 启用时仅 write-through 到 PG，List/Get 仍读进程内 map，Gateway 重启后 API 不可见。本批让有 metadata store 时 List/Get/Delete 及父资源校验以 PostgreSQL 为准。

## 实现

- 扩展 `ports.NetworkResourceStore` / `ports.StorageResourceStore`：新增 List/Get（及 route 的 `ListRoutes`/`GetRoute`）。
- 新增 `pkg/adapters/runtime/network_store_reads.go`、`storage_store_reads.go`：从 `network_*` / `storage_*` 表读取。
- 修改 `LocalNetworkService` / `LocalStorageService`：
  - 注入 metadata store 时 List/Get/Delete 委托 PG；
  - Create 路径的 VPC/Volume/Filesystem 父资源校验走 `lookupVPC` / `lookupVolume` / `lookupFilesystem`；
  - `GetStorageObjectDownload` 复用 `GetObject` 读路径。
- 无新 migration（复用 migration 005/006/020 既有表）。
- 新增 `make validate-gateway-metadata-p2`。

## 覆盖范围

| 资源 | List/Get/Delete 读 PG |
|------|----------------------|
| VPC / Subnet / SecurityGroup / LoadBalancer / Route | ✅ |
| Volume / Filesystem / Object | ✅ |
| Bucket / Snapshot / MountTarget | ✅（P3） |

## 真实 PostgreSQL 冒烟（2026-06-29）

| 场景 | 结果 |
|------|------|
| `POST /networks/vpcs` → 重启 Gateway → `GET /networks/vpcs/{id}` | 200，`network_vpcs` 有行 |
| `POST /volumes` → 重启 Gateway → `GET /volumes/{id}` | 200，`storage_volumes` 有行 |

**PASS**

## 边界

- 不改 Core OpenAPI；不声明 real-provider / production ready。
- 快照、挂载目标、bucket 元数据 PG 持久化见 `GATEWAY-METADATA-PERSISTENCE-P3`（`gateway-metadata-persistence-p3.md`）。

## 验证

```bash
cd repo
make validate-gateway-metadata-p2
make validate-gateway-metadata-p1
go test ./pkg/adapters/runtime/... ./services/ani-gateway/... -count=1
```

结果：上述 gate 与测试通过；真实 PG 冒烟通过。
