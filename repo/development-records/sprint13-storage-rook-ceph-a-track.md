# Sprint 13 S03 - Storage snapshots / mount-targets Rook-Ceph A-track

> 记录类型：Sprint 13 A-track completion record
> 日期：2026-06-19
> 范围：ANI Core only
> 状态：A-track historical record；后续 B-track live result 已通过，见 [`sprint13-storage-rook-ceph-live-result.md`](sprint13-storage-rook-ceph-live-result.md)

## 目标

把 Sprint 12 已落地的 `createVolumeSnapshot`、`listVolumeSnapshots` 和 `listFilesystemMountTargets` 从 Tier1 local profile 扩展到 Rook-Ceph / CSI snapshot / NFS 或等价 filesystem backend 的真实 provider contract 代码边界。A 轨只做 adapter contract、fake/mock 单测、契约级 live-gate 和文档闭环；不执行真实 `kubectl apply`、CSI snapshot、NFS/Service 写入或 live gate。

## 实现

- `pkg/adapters/runtime/storage_renderer.go`
  - 新增 `KubernetesStorageRenderer.RenderVolumeSnapshot`，渲染 `snapshot.storage.k8s.io/v1` `VolumeSnapshot` contract manifest，source 指向现有 PVC 名称。
  - 新增 `KubernetesStorageRenderer.RenderFilesystemMountTarget`，渲染 Kubernetes `Service` contract manifest，表达 filesystem mount-target 的只读 contract intent。
- `pkg/adapters/runtime/provider_dryrun.go`
  - Kubernetes dry-run allowlist 新增 `VolumeSnapshot` / `snapshot.storage.k8s.io/v1`。
- `pkg/adapters/runtime/kubernetes_rest_client.go`
  - Kubernetes resource mapping 新增 `VolumeSnapshot` → `/apis/snapshot.storage.k8s.io/v1/namespaces/{namespace}/volumesnapshots/{name}`。
- `pkg/adapters/runtime/*_test.go`
  - fake/mock 单测覆盖 VolumeSnapshot renderer、mount-target Service renderer、storage provider dry-run，以及 Kubernetes REST client VolumeSnapshot apply path。
- `deploy/real-k8s-lab/storage-live-gate.yaml`
  - 新增 `SPRINT13-STORAGE-ROOK-CEPH-A` storage live gate contract。
- `scripts/validate_storage_live_gate.py`
  - 新增 contract validator，固定 Core volume create、snapshot create/list、filesystem create、mount-target list 五个 check；`--live` 保持 human-gated，不在 A 轨自动执行。

## 边界

- 未修改 `ports.StorageService` 签名。
- 未修改 Gateway handler。
- 未新增 `/api/v1/svc`。
- 未执行真实服务器/集群写操作。
- 未把 snapshot/mount-target 标记为 real-provider/runtime/production ready。

## 验证

已执行最终门禁：

```bash
cd repo && make test && make validate-storage-alpha validate-storage-live-gate && python scripts/validate_yaml.py api/openapi/v1.yaml && make validate-doc-entrypoints && git diff --check
```

关键输出：

```text
component import guard passed
auth gateway contract valid
PASS
storage alpha contract valid
SPRINT13-STORAGE-ROOK-CEPH-A contract valid; live execution is human-gated
Ran 6 tests in 0.008s
OK
validated 1 YAML files
document entrypoint boundaries valid
git diff --check passed
```

## 后续 B 轨

后续 B 轨已在人工确认真实 namespace、storage class、snapshot class、filesystem backend、kubeconfig/token 来源后执行 human-gated live gate，并归档非敏感 evidence。当前结论以 [`sprint13-storage-rook-ceph-live-result.md`](sprint13-storage-rook-ceph-live-result.md) 为准；该结论只证明 S03 real-provider evidence passed，不代表 production ready。
