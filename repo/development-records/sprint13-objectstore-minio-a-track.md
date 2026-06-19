# Sprint 13 S05 - object-store bucket/upload/download MinIO A-track

> 记录类型：Sprint 13 A-track completion record
> 日期：2026-06-19
> 范围：ANI Core only
> 状态：code+contract ready, LIVE PENDING

## 目标

把 Sprint 12 已落地的 storage bucket、object upload/download 预签名 URL 能力从 Tier1 local profile 扩展到 MinIO / S3 compatible object store 的真实 provider contract 代码边界。A 轨只做 adapter 代码、fake/mock 单测、契约级 live-gate 和文档闭环；不部署 MinIO、不执行真实 object PUT/GET、不跑真实 live gate。

## 实现

- `pkg/adapters/objectstore/minio_store.go`
  - 新增 `MinIOObjectStore`，实现既有 `ports.ObjectStore`。
  - `EnsureBucket` 使用 signed `HEAD /bucket` + signed `PUT /bucket`，已有 bucket 幂等成功。
  - `SignedUploadURL` / `SignedDownloadURL` 使用 AWS SigV4 生成 S3-compatible pre-signed URL，路径按 `bucket/tenant/object_key` 组织；upload/download 仍为预签名 URL 流程，不走 multipart。
  - `PutObject` / `GetObject` / `StatObject` / `DeleteObject` 提供 HTTP/SigV4 基础实现，错误按 `ports.Err*` fail closed 映射。
- `pkg/bootstrap/deps.go` / `pkg/bootstrap/server.go`
  - 新增显式 `OBJECT_STORE_PROVIDER=minio` 配置路径，构造 MinIO object store 并注入 `StorageResources`。
  - 默认配置保持 `objectstore.NotConfigured{}` 且不注入 `StorageResources`，Gateway dev/local profile 语义不变。
- `deploy/real-k8s-lab/object-store-live-gate.yaml`
  - 新增 `SPRINT13-OBJECTSTORE-MINIO-A` object-store live gate contract。
- `scripts/validate_object_store_live_gate.py`
  - 新增 contract validator，固定 MinIO readiness、Core bucket create/list、upload pre-signed URL、download pre-signed URL 五个 check；`--live` 保持 human-gated，不在 A 轨自动执行。

## 边界

- 未修改 `ports.ObjectStore` / `ports.StorageService` 签名。
- 未修改 Gateway handler。
- 未新增 `/api/v1/svc`。
- 未执行真实服务器/集群写操作。
- 未把 object-store bucket/upload/download 标记为 real-provider/runtime/production ready。

## 验证

已执行最终门禁：

```bash
cd repo && make test && make validate-storage-alpha validate-object-store-live-gate && python scripts/validate_yaml.py api/openapi/v1.yaml && make validate-doc-entrypoints && git diff --check
```

关键输出：

```text
component import guard passed
auth gateway contract valid
PASS
storage alpha contract valid
TestMinIOObjectStoreBuildsTenantScopedSignedUploadAndDownloadURLs PASS
TestNewCapabilitiesCanWireMinIOObjectStoreProvider PASS
SPRINT13-OBJECTSTORE-MINIO-A contract valid; live execution is human-gated
Ran 6 tests in 0.008s
OK
validated 1 YAML files
document entrypoint boundaries valid
git diff --check passed
```

## 后续 B 轨

人工确认真实 MinIO endpoint、TLS、access policy、bucket prefix、租户隔离策略和 evidence 输出路径后，执行 human-gated live gate 并归档非敏感 evidence。真实 evidence 归档前，S05 保持 Tier1 local profile / LIVE PENDING。
