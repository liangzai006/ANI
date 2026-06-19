# SPRINT13-K8S-WORKLOADS-VCLUSTER-LIVE-A — K8s workloads vCluster live gate 结果

> 记录类型：Sprint 13 B-track live result
> 完成日期：2026-06-20
> 范围：仅 ANI Core S02 K8s workloads vCluster workload list evidence；不代表 production ready
> 状态：**real-provider evidence passed for S02 workload list gate**

## 目标

在人工确认真实写操作后，对 Sprint 13 S02 K8s workloads vCluster 执行真实 live gate，证明 Core 可经既有 vCluster proxy target / Kubernetes API 路径观察真实 vCluster 内的 Deployment workload，并在成功后清理临时 workload。

## §153 五项实测结果

| 项 | 实测结果 |
|---|---|
| 当前状态 | S02 K8s workloads vCluster real-provider evidence passed。`validate-vcluster-live-gate` 已覆盖 Helm chart version pin、vCluster `/version`、临时 Deployment create、Core cluster register、Core proxy `/version`、Core workload list observe 与 cleanup。 |
| 真实组件 + 版本 | 宿主 Kubernetes `v1.36.1`；vCluster Helm chart/app 固定恢复为 `0.34.1`；vCluster API evidence 返回 Kubernetes `v1.35.0`；vCluster CLI 恢复为 `v0.34.1`。 |
| live gate 命令 | `python scripts/validate_vcluster_live_gate.py --live --tenant-id tenant-a --namespace ani-tenant-tenant-a-vcluster --cluster-id k8sclu-live --gateway-url http://127.0.0.1:8080/api/v1 --ani-bearer-token dev-token --vcluster-binary /private/tmp/vcluster-v0.34.1-darwin-arm64 --proxy-server http://127.0.0.1:18002 --chart-version 0.34.1 --evidence-output development-records/live-evidence/sprint13-k8s-workloads-vcluster-live-evidence.json` |
| evidence 输出路径 | `repo/development-records/live-evidence/sprint13-k8s-workloads-vcluster-live-evidence.json` |
| 失败边界 | 本次只证明 S02 workload list real-provider evidence passed；不代表 production ready，不证明生产 per-cluster metadata target、KMS token 管理、长期 workload 生命周期管理、跨 namespace 策略或 S03-S07 完成。 |

## 关键输出

```text
M1-K8S-LIVE-A live checks valid; evidence written to development-records/live-evidence/sprint13-k8s-workloads-vcluster-live-evidence.json
```

Evidence 摘要：

```json
{
  "cleanup": "deleted",
  "core_cluster_id": "k8sclu-22cb0b6a-1fc2-4eb2-b487-528d1601a9fd",
  "id": "vcluster-live-gate",
  "kubectl_version": "v1.35.0",
  "profile": "M1-K8S-LIVE-A",
  "proxy_status": 200,
  "status": "passed",
  "workload_count": 1,
  "workload_name": "ani-s02-live-workload",
  "workloads_status": 200
}
```

## 恢复与清理核验

- 已恢复 vCluster CLI：`/private/tmp/vcluster-v0.34.1-darwin-arm64 --version` 返回 `vcluster version 0.34.1`。
- 本次发现 validator 未 pin chart version 会升级到最新 chart，已修正为默认 `--version 0.34.1`；误触发的 `vcluster-0.35.0` revision 已回滚到 `vcluster-0.34.1` 轨道。
- vCluster StatefulSet 已恢复 `1/1 Running`，Helm release `deployed`。
- 临时 Deployment `ani-s02-live-workload` 在 vCluster `default` namespace 中已删除，cleanup 查询返回 NotFound。

## 代码与契约边界

- `scripts/validate_vcluster_live_gate.py` 保持默认 vCluster CLI connect 路径，同时新增显式 `--proxy-server` 稳定路径，用于已由 vCluster CLI 打开的本地 Kubernetes API proxy。
- live gate 固定 `VCLUSTER_CHART_VERSION=0.34.1` 默认值，避免未来执行时隐式升级真实组件。
- Core workload observe 仍经 Gateway `/api/v1/k8s-clusters/{id}/workloads`，handler 与 `ports.K8sClusterService` 签名不变。
- evidence 不记录 token、kubeconfig、服务器 IP 或 workload 敏感内容。

## 非目标

- 不声明 K8s workloads production ready。
- 不声明 S03-S07 已完成真实 live gate。
- 不把本机 kubectl proxy 路径等同于生产 per-cluster metadata resolver、TLS/credential 管理或长期租户集群生命周期能力。
