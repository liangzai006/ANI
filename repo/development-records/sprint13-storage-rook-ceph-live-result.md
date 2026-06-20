# SPRINT13-STORAGE-ROOK-CEPH-LIVE-A - Storage Rook-Ceph live gate result

> 记录类型：Sprint 13 B-track production-shaped live result
> 完成日期：2026-06-20
> 范围：ANI Core S03 volume / snapshot / filesystem mount-target provider
> 状态：**production-shaped gate passed**；不代表 full platform production ready

## §153 五项实测结果

| 项 | 实测结果 |
|---|---|
| 当前状态 | S03 已重新执行 `--production-shaped` live gate 并通过。Gateway 使用集群内 ServiceAccount/RBAC 访问真实 Kubernetes/Rook-Ceph，执行 PVC、VolumeSnapshot、filesystem PVC 与 mount-target Service create/observe/cleanup。 |
| 真实组件 + 版本 | Kubernetes `v1.36.1`；Rook `v1.20.0`；Ceph `v19.2.3`；RBD StorageClass `ani-rbd-ssd`；VolumeSnapshotClass `csi-rbdplugin-snapclass`。 |
| live gate 命令 | `python3 scripts/validate_storage_live_gate.py --live --production-shaped --gateway-url http://ani-gateway.ani-system.svc:8080/api/v1 --ani-bearer-token <redacted> --tenant-id tenant-a --namespace ani-tenant-tenant-a --storage-class ani-rbd-ssd --snapshot-class csi-rbdplugin-snapclass --kubeconfig /tmp/incluster.kubeconfig --evidence-output development-records/live-evidence/sprint13-storage-rook-ceph-live-evidence.json` |
| evidence 输出路径 | `repo/development-records/live-evidence/sprint13-storage-rook-ceph-live-evidence.json` |
| 边界 | Production-shaped gate passed 只证明 S03 provider、in-cluster RBAC、snapshot 与 backup/restore-shaped lifecycle 门禁通过；不代表 production ready / full platform release，不代表业务数据面长期读写、备份策略 SLA 或 Ceph 运维策略全部完成。 |

## Evidence 摘要

```json
{
  "volume_status": 201,
  "snapshot_status": 202,
  "filesystem_status": 201,
  "mount_target_count": 1,
  "cleanup": "deleted",
  "production_shape": {
    "status": "passed",
    "transport_profile": "in_cluster_serviceaccount",
    "missing_items": [],
    "proof_items": [
      "production_gateway",
      "in_cluster_serviceaccount_rbac",
      "tenant_storage_lifecycle_and_backup_restore"
    ]
  }
}
```

## 代码与部署闭环

- `validate_storage_live_gate.py --production-shaped` 拒绝本地 Gateway evidence。
- 本次使用真实 `ani-rbd-ssd` 与 `csi-rbdplugin-snapclass`；临时 PVC、VolumeSnapshot、Service 均已 cleanup。
