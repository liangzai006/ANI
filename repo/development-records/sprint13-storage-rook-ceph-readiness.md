# Sprint 13 切片 03 — Storage snapshots / mount-targets Rook-Ceph real provider 就绪声明

> 记录类型：Per-slice readiness（ANI-06「真实底座组件引入强制门禁」§153 的执行前声明）
> 工件归属：Sprint 13 / Core real provider 与 live gate 收敛
> 执行地图：[`sprint13-real-provider-readiness-plan.md`](sprint13-real-provider-readiness-plan.md)
> 状态：**production-shaped gate passed for S03 storage snapshot / mount-target gate**（A 轨与 B 轨 live gate 均已完成；`production_shape.status=passed`）。不代表 full platform production ready。

---

## 0. 已核对的真实事实（禁止臆测）

1. Sprint 12 已落地 storage snapshot / mount-target 契约与本地实现：`ports.StorageService.CreateVolumeSnapshot`、`ListVolumeSnapshots`、`ListFilesystemMountTargets`（`pkg/ports/storage_resources.go`），网关 `storage_resources.go` 返回 schema 对齐的 `AsyncTask` / `{items,total,next_cursor}`。
2. 既有 storage provider 代码边界：`StorageProviderRenderer`、`StorageProviderDryRun`、`StorageProviderApply`、`StorageProviderStatusReader`、`KubernetesStorageRenderer`、`KubernetesStorageProviderAdapter`、`KubernetesRESTClient`。现有 renderer 已覆盖 PVC / ObjectMetadata intent，尚未覆盖 snapshot / mount-target intent。
3. Sprint 11 已完成 Rook-Ceph 正式部署、RBD smoke、KubeVirt VM RBD storage smoke 与 reboot resilience；这些是历史底座证据，不等同于 Sprint 13 snapshot/mount-target API 的 live evidence。
4. S03 A 轨当时只允许新增 renderer / adapter contract 与 fake/mock 单测、契约级 live-gate；B 轨已在人工确认后安装/恢复 CSI snapshot CRDs/controller、创建 RBD `VolumeSnapshotClass`，并通过真实 Core live gate。

## 1. §153 五项声明

| 项 | 内容 |
|---|---|
| **当前状态** | S03 storage snapshot / mount-target production-shaped gate passed；`LocalStorageService` 在显式 provider 配置下可对 volume、filesystem、snapshot 与 mount-target 执行 `Render -> DryRun -> Apply -> Observe`，Gateway 可注入 provider-backed `ports.StorageService` 并经 in-cluster ServiceAccount/RBAC 访问 Kubernetes/Rook-Ceph。 |
| **真实组件 + 版本** | Kubernetes `v1.36.1`；Rook `v1.20.0`；Ceph `v19.2.3`；CSI driver `rook-ceph.rbd.csi.ceph.com`；snapshot CRDs 已安装；运行中的 `snapshot-controller` 镜像为 `registry.k8s.io/sig-storage/snapshot-controller:v8.4.0`；Rook RBD CSI ctrlplugin sidecar `csi-snapshotter` 为 `registry.k8s.io/sig-storage/csi-snapshotter:v8.5.0`；StorageClass `ani-rbd-ssd`；VolumeSnapshotClass `csi-rbdplugin-snapclass`。 |
| **live gate 命令** | `python scripts/validate_storage_live_gate.py --live --production-shaped --gateway-url <in-cluster-core-api>/api/v1 --ani-bearer-token <redacted> --tenant-id <tenant> --namespace <tenant-namespace> --storage-class ani-rbd-ssd --snapshot-class csi-rbdplugin-snapclass --filesystem-backend nfs --kubeconfig <in-cluster-kubeconfig> --evidence-output development-records/live-evidence/sprint13-storage-rook-ceph-live-evidence.json` |
| **evidence 输出路径** | `repo/development-records/sprint13-storage-rook-ceph-live-result.md` + `repo/development-records/live-evidence/sprint13-storage-rook-ceph-live-evidence.json`。 |
| **失败边界（不得声称）** | S03 已可标 production-shaped acceptance passed；仍不得标 full platform production ready，不证明长期租户存储生命周期、PVC 真实数据面读写、备份/恢复策略、CephFS/NFS 后端生产形态或 S04-S07 完成。 |

## 2. 代码边界

- 已复用 `KubernetesStorageRenderer` 和 `KubernetesStorageProviderAdapter`，新增 snapshot/mount-target contract manifest，并通过 `STORAGE_PROVIDER=kubernetes_rest` 显式注入到 Gateway。
- 不改 `ports.StorageService` 签名，不改 Gateway handler，不新增 `/api/v1/svc`。
- 新增 Kubernetes manifest 仍通过既有 `ports.WorkloadManifest` 与 provider dry-run/apply boundary；handler 不直接拼接真实集群操作。
- 失败必须 fail closed：unsupported provider/kind、manifest 非法、identity 不匹配或未 dry-run accepted 均返回错误。

## 3. 真实服务器安全

- B 轨已由人工确认并执行真实写操作；凭据未写入可提交文件或回复。
- 本次安装/恢复 CSI snapshot CRDs/controller，并创建 `csi-rbdplugin-snapclass`；临时 PVC、VolumeSnapshot 与 filesystem mount-target Service 已由 live gate cleanup 删除。

## 4. 完成判定

```bash
cd repo && make test && make validate-storage-alpha validate-storage-live-gate && python scripts/validate_yaml.py api/openapi/v1.yaml && make validate-doc-entrypoints && git diff --check
```

B 轨 live gate 通过输出：

```text
SPRINT13-STORAGE-ROOK-CEPH-A live checks valid; evidence written to development-records/live-evidence/sprint13-storage-rook-ceph-live-evidence.json
```

## 5. 关联文档

- Sprint 13 执行地图：[`sprint13-real-provider-readiness-plan.md`](sprint13-real-provider-readiness-plan.md)
- 当前冲刺入口：[`../CURRENT-SPRINT.md`](../CURRENT-SPRINT.md)
- Sprint 11 storage historical evidence：`sprint11-rook-ceph-live-deployment-result.yaml`、`sprint11-rook-ceph-vm-storage-smoke-result.yaml`、`sprint11-rook-ceph-reboot-resilience-result.yaml`
- S03 A 轨记录：[`sprint13-storage-rook-ceph-a-track.md`](sprint13-storage-rook-ceph-a-track.md)
- S03 B 轨 live result：[`sprint13-storage-rook-ceph-live-result.md`](sprint13-storage-rook-ceph-live-result.md)
- 代码：`pkg/ports/storage_resources.go`、`pkg/adapters/runtime/storage_service.go`、`pkg/adapters/runtime/storage_renderer.go`、`pkg/adapters/runtime/storage_provider.go`、`services/ani-gateway/internal/router/storage_resources.go`
