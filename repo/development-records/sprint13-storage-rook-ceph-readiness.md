# Sprint 13 切片 03 — Storage snapshots / mount-targets Rook-Ceph real provider 就绪声明

> 记录类型：Per-slice readiness（ANI-06「真实底座组件引入强制门禁」§153 的执行前声明）
> 工件归属：Sprint 13 / Core real provider 与 live gate 收敛
> 执行地图：[`sprint13-real-provider-readiness-plan.md`](sprint13-real-provider-readiness-plan.md)
> 状态：**code+contract ready, LIVE PENDING**（A 轨已完成；尚未跑通真实 live gate）。在 evidence 产出前，volume snapshot 与 filesystem mount-target 只可标 Tier1 local profile。

---

## 0. 已核对的真实事实（禁止臆测）

1. Sprint 12 已落地 storage snapshot / mount-target 契约与本地实现：`ports.StorageService.CreateVolumeSnapshot`、`ListVolumeSnapshots`、`ListFilesystemMountTargets`（`pkg/ports/storage_resources.go`），网关 `storage_resources.go` 返回 schema 对齐的 `AsyncTask` / `{items,total,next_cursor}`。
2. 既有 storage provider 代码边界：`StorageProviderRenderer`、`StorageProviderDryRun`、`StorageProviderApply`、`StorageProviderStatusReader`、`KubernetesStorageRenderer`、`KubernetesStorageProviderAdapter`、`KubernetesRESTClient`。现有 renderer 已覆盖 PVC / ObjectMetadata intent，尚未覆盖 snapshot / mount-target intent。
3. Sprint 11 已完成 Rook-Ceph 正式部署、RBD smoke、KubeVirt VM RBD storage smoke 与 reboot resilience；这些是历史底座证据，不等同于 Sprint 13 snapshot/mount-target API 的 live evidence。
4. S03 A 轨只允许新增 renderer / adapter contract 与 fake/mock 单测、契约级 live-gate；不执行 `kubectl apply`、CSI snapshot 创建、NFS/Service 写入或任何真实集群状态变更。

## 1. §153 五项声明

| 项 | 内容 |
|---|---|
| **当前状态** | contract + Tier1 local profile；`LocalStorageService` 当前可返回本地 snapshot 与 mount-target 记录；A 轨已补 `VolumeSnapshot` 与 mount-target `Service` provider contract manifest。 |
| **真实组件 + 版本** | Rook-Ceph RBD / CSI snapshot / NFS 或 CephFS mount-target；已部署 Rook `v1.20.0`、Ceph `v19.2.3`，CSI snapshot CRD 与 storage class 细节需 B 轨执行前在真实 lab 只读确认。 |
| **live gate 命令** | 本地契约：`make validate-storage-alpha validate-storage-live-gate`；真实 B 轨为 human-gated，需在执行脚本 live 模式前由人工确认 backend 与 evidence 输出路径。 |
| **evidence 输出路径** | `repo/development-records/sprint13-storage-rook-ceph-live-result.md` + 非敏感 evidence JSON。 |
| **失败边界（不得声称）** | 若 snapshot/mount-target 未在真实 Rook-Ceph/CSI/NFS 或等价后端跑通并归档 evidence，不得标 real-provider / runtime ready / production ready；不得用 Sprint 11 RBD PVC smoke 直接替代当前 Core API snapshot/mount-target evidence。 |

## 2. 代码边界

- A 轨优先复用 `KubernetesStorageRenderer` 和 `KubernetesStorageProviderAdapter`，只新增 snapshot/mount-target contract manifest。
- 不改 `ports.StorageService` 签名，不改 Gateway handler，不新增 `/api/v1/svc`。
- 新增 Kubernetes manifest 仍通过既有 `ports.WorkloadManifest` 与 provider dry-run/apply boundary；不在 handler 或 service 里直接拼接真实集群操作。
- 失败必须 fail closed：unsupported provider/kind、manifest 非法、identity 不匹配或未 dry-run accepted 均返回错误。

## 3. 真实服务器安全

- A 轨不执行 Helm/kubectl apply，不创建 `VolumeSnapshot`、PVC、Service、EndpointSlice 或 NFS/CephFS 资源。
- B 轨执行前必须由人工确认 namespace、storage class、snapshot class、filesystem backend、token/kubeconfig 来源和证据输出路径；凭据不得写入可提交文件或回复。

## 4. 完成判定（A 轨）

```bash
cd repo && make test && make validate-storage-alpha validate-storage-live-gate && python scripts/validate_yaml.py api/openapi/v1.yaml && make validate-doc-entrypoints && git diff --check
```

## 5. 关联文档

- Sprint 13 执行地图：[`sprint13-real-provider-readiness-plan.md`](sprint13-real-provider-readiness-plan.md)
- 当前冲刺入口：[`../CURRENT-SPRINT.md`](../CURRENT-SPRINT.md)
- Sprint 11 storage historical evidence：`sprint11-rook-ceph-live-deployment-result.yaml`、`sprint11-rook-ceph-vm-storage-smoke-result.yaml`、`sprint11-rook-ceph-reboot-resilience-result.yaml`
- S03 A 轨记录：[`sprint13-storage-rook-ceph-a-track.md`](sprint13-storage-rook-ceph-a-track.md)
- 代码：`pkg/ports/storage_resources.go`、`pkg/adapters/runtime/storage_service.go`、`pkg/adapters/runtime/storage_renderer.go`、`pkg/adapters/runtime/storage_provider.go`、`services/ani-gateway/internal/router/storage_resources.go`
