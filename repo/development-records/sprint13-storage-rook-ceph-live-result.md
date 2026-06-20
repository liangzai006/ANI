# SPRINT13-STORAGE-ROOK-CEPH-LIVE-A - Storage snapshots / mount-targets Rook-Ceph live gate result

> 记录类型：Sprint 13 B-track live result
> 完成日期：2026-06-20
> 范围：仅 ANI Core S03 storage snapshot / filesystem mount-target real-provider evidence；不代表 production ready
> 状态：**real-provider evidence passed for S03 storage snapshot / mount-target gate**

## 目标

在人工确认真实写操作后，对 Sprint 13 S03 storage Rook-Ceph 执行真实 live gate，证明 Core 可经 `STORAGE_PROVIDER=kubernetes_rest` 显式 provider 路径创建并观察 RBD PVC、CSI `VolumeSnapshot`、filesystem PVC 与 mount-target `Service` contract，并在成功后清理临时资源。

## §153 五项实测结果

| 项 | 实测结果 |
|---|---|
| 当前状态 | S03 storage snapshot / mount-target real-provider evidence passed。`LocalStorageService` 在显式 provider 配置下执行 `Render -> DryRun -> Apply -> Observe`，Gateway 可注入 provider-backed `ports.StorageService`，handler 不绕过 port。 |
| 真实组件 + 版本 | Kubernetes `v1.36.1`；Rook `v1.20.0`；Ceph `v19.2.3`；CSI driver `rook-ceph.rbd.csi.ceph.com`；CSI external-snapshotter CRD/controller `v8.5.0`；RBD StorageClass `ani-rbd-ssd`；VolumeSnapshotClass `csi-rbdplugin-snapclass`，driver `rook-ceph.rbd.csi.ceph.com`，`deletionPolicy=Delete`，default annotation enabled. |
| live gate 命令 | `python scripts/validate_storage_live_gate.py --live --gateway-url http://127.0.0.1:8080/api/v1 --ani-bearer-token dev-token --tenant-id tenant-a --namespace ani-tenant-tenant-a --storage-class ani-rbd-ssd --snapshot-class csi-rbdplugin-snapclass --filesystem-backend nfs --kubeconfig ../local-secrets/real-k8s-lab.kubeconfig --evidence-output development-records/live-evidence/sprint13-storage-rook-ceph-live-evidence.json` |
| evidence 输出路径 | `repo/development-records/live-evidence/sprint13-storage-rook-ceph-live-evidence.json` |
| 失败边界 | 本次只证明 S03 Core storage snapshot / mount-target real-provider evidence passed；不代表 production ready，不证明长期租户存储生命周期、PVC 真实数据面读写、生产凭据管理、备份/恢复策略、CephFS/NFS 后端生产形态或 S04-S07 完成。 |

## 关键输出

```text
SPRINT13-STORAGE-ROOK-CEPH-A live checks valid; evidence written to development-records/live-evidence/sprint13-storage-rook-ceph-live-evidence.json
```

Evidence 摘要：

```json
{
  "cleanup": "deleted",
  "filesystem_backend": "nfs",
  "filesystem_status": 201,
  "id": "storage-live-gate",
  "mount_target_count": 1,
  "namespace": "ani-tenant-tenant-a",
  "profile": "SPRINT13-STORAGE-ROOK-CEPH-A",
  "snapshot_class": "csi-rbdplugin-snapclass",
  "snapshot_count": 1,
  "snapshot_status": 202,
  "status": "passed",
  "storage_class": "ani-rbd-ssd",
  "tenant_id": "tenant-a",
  "volume_status": 201
}
```

## 组件恢复与清理核验

- 已安装/恢复 CSI snapshot CRDs：`volumesnapshots.snapshot.storage.k8s.io`、`volumesnapshotcontents.snapshot.storage.k8s.io`、`volumesnapshotclasses.snapshot.storage.k8s.io`。
- 已安装/恢复 `snapshot-controller`，namespace `kube-system`，rollout 成功。
- 已创建 RBD `VolumeSnapshotClass`：`csi-rbdplugin-snapclass`，driver `rook-ceph.rbd.csi.ceph.com`，`deletionPolicy=Delete`，并设置 `snapshot.storage.kubernetes.io/is-default-class=true`，以匹配当前 Core snapshot API 未暴露 snapshot class 字段的契约。
- 清理核验：

```text
kubectl get pvc -n ani-tenant-tenant-a -l app.kubernetes.io/managed-by=ani-core
No resources found in ani-tenant-tenant-a namespace.

kubectl get volumesnapshot -n ani-tenant-tenant-a -l app.kubernetes.io/managed-by=ani-core
No resources found in ani-tenant-tenant-a namespace.

kubectl get svc -n ani-tenant-tenant-a -l ani.kubercloud.io/storage-kind=filesystem_mount_target
No resources found in ani-tenant-tenant-a namespace.
```

## 代码与契约边界

- `ports.StorageProviderRenderer` 扩展 `RenderVolumeSnapshot` 与 `RenderFilesystemMountTarget`，仍只通过 port 边界表达 provider intent。
- `runtime.LocalStorageService` 在显式 provider 配置下对 volume、filesystem、snapshot 与 mount-target 执行 `Render -> DryRun -> Apply -> Observe`；未配置 provider 时保持 Tier1 local profile。
- Gateway `RegisterWithOptions` 支持注入 `ports.StorageService`，`services/ani-gateway/main.go` 可由 `STORAGE_PROVIDER=kubernetes_rest` 构造 provider-backed storage service。
- `scripts/validate_storage_live_gate.py --live` 只写非敏感 evidence JSON，不写 bearer token、kubeconfig 内容、服务器 IP 或凭据。

## 非目标

- 不声明 storage production ready 或完整 runtime ready。
- 不声明 S04-S07 已完成真实 live gate。
- 不把本次 NFS protocol contract 等同于生产 NFS/CephFS 数据面挂载能力；本次 mount-target 只证明 Core API 与 Kubernetes `Service` contract create/list/cleanup 路径。
