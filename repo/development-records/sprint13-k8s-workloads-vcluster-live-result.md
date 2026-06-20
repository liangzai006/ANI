# SPRINT13-K8S-WORKLOADS-VCLUSTER-LIVE-A - K8s workloads vCluster live gate result

> 记录类型：Sprint 13 B-track production-shaped live result
> 完成日期：2026-06-20
> 范围：ANI Core S02 K8s workloads vCluster provider / proxy / workload observe
> 状态：**production-shaped gate passed**；不代表 full platform production ready

## §153 五项实测结果

| 项 | 实测结果 |
|---|---|
| 当前状态 | S02 已重新执行 `--production-shaped` live gate 并通过。Gateway 运行在集群内 ServiceAccount/RBAC 路径，Core 通过 provider-backed `createK8sCluster` 创建 vCluster，再经 metadata target TLS 执行 `/version` proxy 与 workload list observe。 |
| 真实组件 + 版本 | vCluster CLI `v0.34.1`；vCluster chart/app `0.34.1`；vCluster API evidence 返回 Kubernetes `v1.35.0`；RBD StorageClass `ani-rbd-ssd`。 |
| live gate 命令 | `python3 scripts/validate_vcluster_live_gate.py --live --production-shaped --gateway-url http://ani-gateway.ani-system.svc:8080/api/v1 --ani-bearer-token <redacted> --tenant-id 11111111-1111-4111-8111-111111111111 --namespace ani-tenant-11111111-1111-4111-8111-111111111111 --cluster-id k8sclu-prodshape-s02 --vcluster-server https://{cluster_id}.ani-tenant-11111111-1111-4111-8111-111111111111:443 --kubeconfig /tmp/incluster.kubeconfig --chart-name /tmp/vcluster-0.34.1.tgz --chart-repo none --chart-version= --helm-set controlPlane.statefulSet.persistence.volumeClaim.storageClass=ani-rbd-ssd --evidence-output development-records/live-evidence/sprint13-k8s-workloads-vcluster-live-evidence.json` |
| evidence 输出路径 | `repo/development-records/live-evidence/sprint13-k8s-workloads-vcluster-live-evidence.json` |
| 边界 | Production-shaped gate passed 只证明 S02 provider、metadata target TLS、Gateway proxy/list 生产形态门禁通过；不代表 production ready / full platform release，不代表 Auth/Dex production gate、镜像仓库发布、长期租户集群策略全部完成。 |

## 关键输出

```text
M1-K8S-LIVE-A live checks valid; evidence written to development-records/live-evidence/sprint13-k8s-workloads-vcluster-live-evidence.json
```

## Evidence 摘要

```json
{
  "core_cluster_id": "k8sclu-60c3ae97-8fa0-4a84-8c45-3061ef495009",
  "kubectl_version": "v1.35.0",
  "proxy_status": 200,
  "workloads_status": 200,
  "workload_count": 1,
  "cleanup": "deleted",
  "production_shape": {
    "status": "passed",
    "transport_profile": "metadata_target_tls",
    "missing_items": [],
    "proof_items": [
      "production_gateway",
      "production_per_cluster_metadata_target",
      "production_tls_and_token_management"
    ]
  }
}
```

## 代码与部署闭环

- `validate_vcluster_live_gate.py --production-shaped` 不再预装第二个 vCluster；它由 Gateway provider 创建真实 vCluster，再使用返回的 Core cluster ID 校验 metadata target。
- `VCLUSTER_PROXY_SERVER_TEMPLATE` 与 `VCLUSTER_KUBECONFIG_SERVER_TEMPLATE` 固定为 `https://{cluster_id}.{namespace}:443`，避免 `.svc` 后缀与 vCluster 0.34.1 证书 SAN 不匹配。
- `K8sClusterProxyTarget` 支持 BearerToken 与 mTLS kubeconfig credential；vCluster 0.34.1 当前使用 client certificate/key。
- 本次使用 UUID tenant 以匹配 metadata/RLS schema；临时 workload 与本次创建的 vCluster release/PVC 已清理。
