# SPRINT13-GPU-INVENTORY-DCGM-LIVE-A - GPU inventory / occupancy live gate result

> 记录类型：Sprint 13 B-track live result / real provider evidence
> 日期：2026-06-20
> 范围：仅 ANI Core S04 GPU inventory / occupancy real provider live gate；不代表 production ready
> 状态：**real-provider evidence passed for S04 GPU inventory gate**。S05-S07 仍保持 LIVE PENDING。

## 目标

在 S04 A 轨 `KubernetesGPUInventory` 与 Gateway/Bootstrap `GPU_INVENTORY_PROVIDER=kubernetes_rest` 接线基础上，恢复真实 DCGM metrics 后端，并用 Core `/gpu-inventory`、`/gpu-inventory/occupancy`、Kubernetes NodeList GPU capacity 与 DCGM `DCGM_FI_DEV_GPU_UTIL` 共同证明 GPU inventory / occupancy real-provider gate。

## §153 五项实测结果

| 项 | 实测结果 |
|---|---|
| 当前状态 | S04 B 轨真实 live gate 已通过；Core `/gpu-inventory` 与 `/gpu-inventory/occupancy` 在 `GPU_INVENTORY_PROVIDER=kubernetes_rest` 下返回 real provider `dev_profile`，并与 Kubernetes NodeList GPU capacity、DCGM metrics 同时闭合。 |
| 真实组件 + 版本 | Kubernetes `v1.36.1`；containerd `2.2.4`；NVIDIA device-plugin DaemonSet `nvidia-device-plugin-daemonset` 为 `3/3 ready`，镜像 `nvcr.io/nvidia/k8s-device-plugin:v0.19.2`；DCGM exporter Helm release `ani-dcgm-exporter` 部署于 `ani-system`，chart/app version `4.8.2`，DaemonSet `3/3 ready`，镜像 `nvcr.io/nvidia/k8s/dcgm-exporter:4.5.3-4.8.2-distroless`；三台节点合计 6 GPU。 |
| live gate 命令 | Contract/local：`make validate-gpu-contracts validate-gpu-inventory-live-gate`；真实命令形态：`python scripts/validate_gpu_inventory_live_gate.py --live --gateway-url <core-api>/api/v1 --ani-bearer-token <redacted> --kubernetes-nodes-url <kubectl-proxy>/api/v1/nodes --dcgm-metrics-url <dcgm-metrics-url> --evidence-output development-records/live-evidence/sprint13-gpu-inventory-dcgm-live-evidence.json`。 |
| evidence 输出路径 | 通过型 live evidence：`repo/development-records/live-evidence/sprint13-gpu-inventory-dcgm-live-evidence.json`；只读盘点 evidence 保留为 `repo/development-records/live-evidence/sprint13-gpu-inventory-dcgm-readonly-evidence.json`。 |
| 边界 | S04 只可标 `real-provider evidence passed for GPU inventory gate`；不得标 production ready、runtime ready、S05-S07 完成或整 Sprint 13 完成。DCGM exporter 作为 Sprint 13 lab 支撑组件存在，不代表生产部署方案冻结。 |

## 实测输出摘要

```text
helm release:
ani-dcgm-exporter  namespace=ani-system  status=deployed  chart=dcgm-exporter-4.8.2  appVersion=4.8.2

dcgm exporter daemonset:
3/3 ready image=nvcr.io/nvidia/k8s/dcgm-exporter:4.5.3-4.8.2-distroless

nvidia-device-plugin-daemonset:
3/3 ready image=nvcr.io/nvidia/k8s-device-plugin:v0.19.2

Core live gate:
SPRINT13-GPU-INVENTORY-DCGM-A live checks valid; evidence written to development-records/live-evidence/sprint13-gpu-inventory-dcgm-live-evidence.json
```

## evidence 摘要

```json
{
  "dcgm_metric_present": true,
  "gpu_capacity_total": 6,
  "gpu_node_count": 3,
  "id": "gpu-inventory-live-gate",
  "inventory_count": 6,
  "inventory_status": 200,
  "occupancy_status": 200,
  "occupancy_total": 6,
  "profile": "SPRINT13-GPU-INVENTORY-DCGM-A",
  "status": "passed"
}
```

## 本次代码闭环

- `scripts/validate_gpu_inventory_live_gate.py --live` 新增 `--kubernetes-nodes-url`，可通过本地 `kubectl proxy` 读取 NodeList，避免 Codex 沙箱直接访问真实 API 时失败；未提供时仍保留原 `kubectl get nodes -o json` 路径。
- `default_json_getter` 与 `default_text_getter` 对网络读取失败返回 gate 错误，不输出 Python traceback。
- `deploy/real-k8s-lab/gpu-inventory-live-gate.yaml` 状态更新为 `live`，并记录 NodeList URL + DCGM metrics URL 的可复跑命令形态。
- Evidence JSON 不写 bearer token、kubeconfig 内容、服务器 IP、Pod IP 或凭据。

## 后续

S04 已闭环；下一步仍只能在人工确认后进入 S05/S06/S07 的 B 轨真实 live gate。未完成的切片继续保持 LIVE PENDING。
