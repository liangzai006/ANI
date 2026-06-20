# SPRINT13-GPU-INVENTORY-DCGM-B-TRACK-READONLY - GPU inventory / occupancy live gate read-only result

> 记录类型：Sprint 13 B-track read-only result / live gate blocker
> 日期：2026-06-20
> 范围：仅 ANI Core S04 GPU inventory / occupancy real provider 只读盘点与 gate 能力补齐；不代表 production ready
> 状态：**LIVE PENDING / BLOCKED on DCGM exporter evidence**。不得标 real-provider evidence passed。

## 目标

进入 Sprint 13 S04 B 轨前，先对真实 lab 做只读盘点，并补齐 Core Gateway `GPU_INVENTORY_PROVIDER=kubernetes_rest` 显式接线路径与 `validate-gpu-inventory-live-gate --live` 参数化执行能力。若真实 DCGM metrics 后端不可用，则停止在 LIVE PENDING，不用历史 GPU smoke 或 device-plugin capacity 替代当前 Core API + DCGM live evidence。

## §153 五项实测结果

| 项 | 实测结果 |
|---|---|
| 当前状态 | 已进入 S04 B 轨并完成只读盘点；Core 代码已支持 Gateway/Bootstrap 显式注入 Kubernetes GPU inventory provider，live gate 脚本支持真实 Core `/gpu-inventory`、`/gpu-inventory/occupancy` 与 DCGM metrics 校验；本次未通过 live gate。 |
| 真实组件 + 版本 | Kubernetes `v1.36.1`；containerd `2.2.4`；NVIDIA device-plugin DaemonSet `nvidia-device-plugin-daemonset` 为 `3/3 ready`，镜像 `nvcr.io/nvidia/k8s-device-plugin:v0.19.2`；三台节点各报告 `nvidia.com/gpu` capacity/allocatable `2/2`，合计 6 GPU；未发现 DCGM exporter pod/service/daemonset/deployment。 |
| live gate 命令 | Contract/local：`make validate-gpu-contracts validate-gpu-inventory-live-gate`；真实命令形态：`python scripts/validate_gpu_inventory_live_gate.py --live --gateway-url <core-api>/api/v1 --ani-bearer-token <redacted> --kubeconfig ../local-secrets/real-k8s-lab.kubeconfig --dcgm-metrics-url <dcgm-metrics-url> --evidence-output development-records/live-evidence/sprint13-gpu-inventory-dcgm-live-evidence.json`。本次因 DCGM metrics URL 未确认/未发现，未执行通过。 |
| evidence 输出路径 | 只读盘点 evidence：`repo/development-records/live-evidence/sprint13-gpu-inventory-dcgm-readonly-evidence.json`；通过型 live evidence 仍待后续写入 `repo/development-records/live-evidence/sprint13-gpu-inventory-dcgm-live-evidence.json`。 |
| 失败边界 | S04 仍保持 LIVE PENDING / BLOCKED，不得标 real-provider evidence passed、runtime ready 或 production ready；device-plugin capacity 与 Sprint 5 GPU smoke 只能作为前置事实，不能替代 Core API + DCGM metrics live gate。 |

## 只读盘点输出摘要

```text
snapshot-controller image observed separately during S03 review:
registry.k8s.io/sig-storage/snapshot-controller:v8.4.0

nvidia-device-plugin-daemonset:
3/3 ready image=nvcr.io/nvidia/k8s-device-plugin:v0.19.2

GPU nodes:
dev-phys-02  capacity=2 allocatable=2 kubelet=v1.36.1 containerd://2.2.4
dev-phys-03  capacity=2 allocatable=2 kubelet=v1.36.1 containerd://2.2.4
kubercloud   capacity=2 allocatable=2 kubelet=v1.36.1 containerd://2.2.4

DCGM resources:
no pod/service/daemonset/deployment matching dcgm|gpu-exporter|nvidia-dcgm was found
```

## 本次代码闭环

- Gateway `RegisterOptions` 新增可选 `ports.GPUInventory` 注入；未配置时仍使用 `LocalGPUInventory`。
- `services/ani-gateway/gpu_inventory_runtime.go` 新增 `GPU_INVENTORY_PROVIDER=kubernetes_rest`，仅构造只读 `KubernetesGPUInventory`。
- `pkg/bootstrap` 新增 `GPUInventoryProvider` 配置与 `GPU_INVENTORY_PROVIDER` 环境变量覆盖；planning runtime 使用同一 inventory port。
- GPU inventory 响应在 provider 注入时返回 `dev_profile.mode=real`、`provider=kubernetes-gpu-inventory`、`real_provider=true`；默认本地 profile 不变。
- `scripts/validate_gpu_inventory_live_gate.py --live` 要求显式 `--dcgm-metrics-url`，并校验 Core API real dev_profile 与 DCGM `DCGM_FI_DEV_GPU_UTIL` 指标；evidence 不写 bearer token、kubeconfig 内容、服务器 IP 或凭据。

## 下一步

需要人工确认是否部署/恢复 DCGM exporter 或提供已有 Prometheus/DCGM metrics endpoint。确认后再执行真实 live gate；跑通前 S04 只保持 LIVE PENDING / BLOCKED。
