# SPRINT13-GPU-INVENTORY-DCGM-LIVE-A - GPU inventory / occupancy live gate result

> 记录类型：Sprint 13 B-track production-shaped live result
> 完成日期：2026-06-20
> 范围：ANI Core S04 GPU inventory / occupancy provider
> 状态：**production-shaped gate passed**；不代表 full platform production ready

## §153 五项实测结果

| 项 | 实测结果 |
|---|---|
| 当前状态 | S04 已重新执行 `--production-shaped` live gate 并通过。Gateway 使用集群内 Kubernetes API 查询 Node GPU capacity，并使用集群内 DCGM exporter Service metrics 校验 GPU inventory / occupancy。 |
| 真实组件 + 版本 | Kubernetes `v1.36.1`；NVIDIA device-plugin `v0.19.2`；DCGM exporter chart/app `4.8.2`；三台节点合计 6 GPU。 |
| live gate 命令 | `python3 scripts/validate_gpu_inventory_live_gate.py --live --production-shaped --gateway-url http://ani-gateway.ani-system.svc:8080/api/v1 --ani-bearer-token <redacted> --kubeconfig /tmp/incluster.kubeconfig --dcgm-metrics-url http://ani-dcgm-exporter.ani-system.svc:9400/metrics --evidence-output development-records/live-evidence/sprint13-gpu-inventory-dcgm-live-evidence.json` |
| evidence 输出路径 | `repo/development-records/live-evidence/sprint13-gpu-inventory-dcgm-live-evidence.json` |
| 边界 | Production-shaped gate passed 只证明 S04 provider、in-cluster Kubernetes API 与 cluster Service metrics 门禁通过；不代表 production ready / full platform release，不代表 GPU 调度、隔离、计费或长期 Prometheus HA 策略全部完成。 |

## Evidence 摘要

```json
{
  "inventory_status": 200,
  "occupancy_status": 200,
  "inventory_count": 6,
  "gpu_capacity_total": 6,
  "dcgm_metric_present": true,
  "production_shape": {
    "status": "passed",
    "transport_profile": "in_cluster_kubernetes_api_and_cluster_metrics_service",
    "missing_items": [],
    "proof_items": [
      "production_gateway",
      "in_cluster_kubernetes_api",
      "production_dcgm_service_or_prometheus_query"
    ]
  }
}
```

## 代码与部署闭环

- `validate_gpu_inventory_live_gate.py --production-shaped` 拒绝 local Kubernetes nodes URL 与本地 DCGM/Prometheus port-forward。
- evidence 不记录 bearer token、kubeconfig、服务器 IP、Pod IP 或凭据。
