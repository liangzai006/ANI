# Sprint 13 切片 05 — object-store bucket/upload/download MinIO real provider 就绪声明

> 记录类型：Per-slice readiness（ANI-06「真实底座组件引入强制门禁」§153 的执行前声明）
> 工件归属：Sprint 13 / Core real provider 与 live gate 收敛
> 执行地图：[`sprint13-real-provider-readiness-plan.md`](sprint13-real-provider-readiness-plan.md)
> 状态：**code+contract ready, LIVE PENDING**（A 轨已完成；尚未跑通真实 live gate）。在 evidence 产出前，对象存储 bucket/upload/download 只可标 Tier1 local profile。

---

## 0. 已核对的真实事实（禁止臆测）

1. Sprint 12 已落地 storage bucket、object upload/download 的 Core API contract：`listStorageBuckets`、`createStorageBucket`、`uploadStorageObject`、`downloadStorageObject` 均在 `storage_resources.go` 经 `ports.StorageService` 暴露。
2. `ports.ObjectStore` 已存在 `EnsureBucket`、`SignedUploadURL`、`SignedDownloadURL` 边界；`LocalStorageService` 在显式注入 object store 时会复用这些 port 方法，upload/download 返回 pre-signed URL，不走 multipart。
3. OpenAPI 已定义 `StorageBucketRecord` / `StorageBucketListResponse` / `StorageObjectUploadRequest` / `StorageObjectUploadResponse` / `StorageObjectDownloadInfo`，POST 请求保留 `idempotency_key`，RBAC scope 保持 `scope:objects:*`。
4. S05 A 轨只允许新增 MinIO/S3 兼容 adapter、fake/mock 单测、契约级 live-gate 和文档闭环；不部署 MinIO，不执行真实上传/下载，不跑真实 live gate。

## 1. §153 五项声明

| 项 | 内容 |
|---|---|
| **当前状态** | contract + Tier1 local profile；Gateway 默认仍使用 local storage profile；A 轨已新增 `MinIOObjectStore` adapter，并在 `OBJECT_STORE_PROVIDER=minio` 显式配置时可注入 `StorageResources`。 |
| **真实组件 + 版本** | MinIO / S3 compatible object store；具体 MinIO 版本、endpoint、access policy、bucket namespace 与 TLS 设置需 B 轨执行前在真实 lab 只读确认。 |
| **live gate 命令** | 本地契约：`make validate-storage-alpha validate-object-store-live-gate`；真实 B 轨：`python scripts/validate_object_store_live_gate.py --live --evidence-output <path>` 的执行仍为 human-gated，需先人工确认 MinIO endpoint 与凭据来源。 |
| **evidence 输出路径** | `repo/development-records/sprint13-objectstore-minio-live-result.md` + 非敏感 evidence JSON；不得归档 access key、secret key、session token 或完整 pre-signed URL。 |
| **失败边界（不得声称）** | 若 `/buckets`、`/objects/upload`、`/objects/{object_id}/download` 未在真实 MinIO 后端跑通并归档 evidence，不得标 real-provider / runtime ready / production ready；不得用 local profile URL 替代 MinIO pre-signed URL evidence。 |

## 2. 代码边界

- A 轨新增 `pkg/adapters/objectstore/MinIOObjectStore`，实现既有 `ports.ObjectStore`，不改 port 接口签名，不改 Gateway handler，不新增 `/api/v1/svc`。
- adapter 使用标准 HTTP + AWS SigV4 生成 S3-compatible pre-signed URL；bucket 创建走 `HEAD /bucket` + `PUT /bucket`，已有 bucket 幂等成功。
- `pkg/bootstrap` 仅在 `OBJECT_STORE_PROVIDER=minio` 显式配置时构造并注入 MinIO object store；默认 dev/local profile 不变，避免把未配置 adapter 误标为 runtime ready。

## 3. 真实服务器安全

- A 轨不部署 MinIO，不创建真实 bucket，不执行真实 object PUT/GET，不写入真实服务器或集群。
- B 轨执行前必须由人工确认 MinIO endpoint、TLS、access policy、bucket prefix、租户隔离策略和 evidence 输出路径；凭据不得写入可提交文件或回复。

## 4. 完成判定（A 轨）

```bash
cd repo && make test && make validate-storage-alpha validate-object-store-live-gate && python scripts/validate_yaml.py api/openapi/v1.yaml && make validate-doc-entrypoints && git diff --check
```

## 5. 关联文档

- Sprint 13 执行地图：[`sprint13-real-provider-readiness-plan.md`](sprint13-real-provider-readiness-plan.md)
- 当前冲刺入口：[`../CURRENT-SPRINT.md`](../CURRENT-SPRINT.md)
- S05 A 轨记录：[`sprint13-objectstore-minio-a-track.md`](sprint13-objectstore-minio-a-track.md)
- 代码：`pkg/ports/object_store.go`、`pkg/adapters/objectstore/minio_store.go`、`pkg/bootstrap/deps.go`、`services/ani-gateway/internal/router/storage_resources.go`
