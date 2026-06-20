# Sprint 13 切片 04 — GPU inventory / occupancy NVIDIA device-plugin + DCGM real provider 就绪声明

> 记录类型：Per-slice readiness（ANI-06「真实底座组件引入强制门禁」§153 的执行前声明）
> 工件归属：Sprint 13 / Core real provider 与 live gate 收敛
> 执行地图：[`sprint13-real-provider-readiness-plan.md`](sprint13-real-provider-readiness-plan.md)
> 状态：**production-shaped gate passed for S04 GPU inventory gate**（A 轨已完成；B 轨已恢复 DCGM exporter，并通过 in-cluster Kubernetes API + cluster Service metrics live gate；`production_shape.status=passed`）。不代表 full platform production ready。

---

## 0. 已核对的真实事实（禁止臆测）

1. Sprint 12 已落地 GPU inventory / occupancy 契约与本地实现：`ports.GPUInventory`（`pkg/ports/gpu_inventory.go`）、`LocalGPUInventory`（`pkg/adapters/runtime/local_gpu_inventory.go`）和 Gateway `gpu_inventory_resources.go`。
2. OpenAPI 已定义 `listGPUInventory` 与 `getGPUOccupancy`，响应 schema 为 `GPUInventoryRecord`、`GPUInventoryListResponse`、`GPUOccupancyStats`，并保留 `x-ani-rbac-scope: scope:gpu-inventory:read`。
3. Sprint 5 已完成三节点 NVIDIA driver、NVIDIA Container Toolkit、device plugin、`nvidia.com/gpu` allocatable 与 GPU smoke Pod 真实验证；这些是 S04 前置事实，不等同于当前 Core API `/gpu-inventory` live evidence。
4. S04 A 轨只允许新增 adapter 只读代码、fake/mock 单测、契约级 live-gate 和文档闭环；不执行真实 `kubectl apply`、DCGM 部署、Prometheus/DCGM 查询或 GPU workload 写操作。
5. 2026-06-20 B 轨只读盘点确认：Kubernetes `v1.36.1`，三台节点各报告 `nvidia.com/gpu` capacity/allocatable `2/2`，NVIDIA device-plugin DaemonSet `3/3 ready`，镜像 `nvcr.io/nvidia/k8s-device-plugin:v0.19.2`；初始未发现 DCGM exporter，因此先停在 LIVE PENDING / BLOCKED。
6. 2026-06-20 经人工确认后恢复 DCGM exporter：Helm release `ani-dcgm-exporter` 部署于 `ani-system`，chart/app version `4.8.2`，DaemonSet `3/3 ready`，镜像 `nvcr.io/nvidia/k8s/dcgm-exporter:4.5.3-4.8.2-distroless`；`validate_gpu_inventory_live_gate.py --live --production-shaped` 已产出通过型 evidence。

## 1. §153 五项声明

| 项 | 内容 |
|---|---|
| **当前状态** | Gateway 默认仍使用 `LocalGPUInventory`；显式 `GPU_INVENTORY_PROVIDER=kubernetes_rest` 时注入 `KubernetesGPUInventory`，Core `/gpu-inventory` 与 `/gpu-inventory/occupancy` 已在 in-cluster ServiceAccount + cluster Service metrics 路径通过 S04 production-shaped live gate。 |
| **真实组件 + 版本** | Kubernetes `v1.36.1`；containerd `2.2.4`；NVIDIA device-plugin DaemonSet `nvidia-device-plugin-daemonset` 为 `3/3 ready`，镜像 `nvcr.io/nvidia/k8s-device-plugin:v0.19.2`；三台节点合计 `nvidia.com/gpu` capacity/allocatable 6；DCGM exporter Helm release `ani-dcgm-exporter`，chart/app version `4.8.2`，DaemonSet `3/3 ready`，镜像 `nvcr.io/nvidia/k8s/dcgm-exporter:4.5.3-4.8.2-distroless`。 |
| **live gate 命令** | 本地契约：`make validate-gpu-contracts validate-gpu-inventory-live-gate`；真实命令形态：`python scripts/validate_gpu_inventory_live_gate.py --live --production-shaped --gateway-url <in-cluster-core-api>/api/v1 --ani-bearer-token <redacted> --kubeconfig <in-cluster-kubeconfig> --dcgm-metrics-url <cluster-service-metrics-url> --evidence-output development-records/live-evidence/sprint13-gpu-inventory-dcgm-live-evidence.json`。 |
| **evidence 输出路径** | 通过型 live gate：`repo/development-records/live-evidence/sprint13-gpu-inventory-dcgm-live-evidence.json`；只读盘点：`repo/development-records/live-evidence/sprint13-gpu-inventory-dcgm-readonly-evidence.json`。 |
| **失败边界（不得声称）** | S04 可标 production-shaped acceptance passed for GPU inventory gate；不得标 full platform production ready、S05-S07 完成或整 Sprint 13 完成；不得用 Sprint 5 GPU smoke Pod 或 device-plugin capacity 替代当前 Core API + DCGM live evidence。 |

## 2. 代码边界

- A 轨已新增 `ports.GPUInventory` 的 Kubernetes 只读 adapter，不改 port 接口签名，不改 Gateway handler，不新增 `/api/v1/svc`。
- B 轨接线补齐 Gateway `GPU_INVENTORY_PROVIDER=kubernetes_rest` 与 bootstrap `GPUInventoryProvider`，仍通过 `ports.GPUInventory` 注入，不在 handler 内直接访问 Kubernetes。
- adapter 只从 Kubernetes Node list 文档解析 node labels、capacity/allocatable `nvidia.com/gpu`、node readiness 和 nodeInfo；DCGM 指标由 live gate 读取 metrics endpoint，不进入 Gateway handler。
- 失败必须 fail closed：Kubernetes API 返回非 2xx、JSON 非法、缺少可识别 GPU 资源时返回空清单或错误，不伪造 runtime ready。

## 3. 真实服务器安全

- A 轨不执行 Helm/kubectl apply，不部署 DCGM exporter，不创建 GPU Pod 或修改 node label。
- B 轨只读盘点未执行集群写操作；后续经人工确认后使用 Helm 部署/恢复 DCGM exporter；凭据未写入可提交文件或回复。
- 后续若需创建 GPU workload 或变更 DCGM exporter 生产部署方案，必须先由人工确认具体写操作、影响范围和清理策略。

## 4. 完成判定

```bash
cd repo && make test && make validate-gpu-contracts validate-gpu-inventory-live-gate && python scripts/validate_yaml.py api/openapi/v1.yaml && make validate-doc-entrypoints && git diff --check
```

真实 live gate：

```bash
cd repo && python scripts/validate_gpu_inventory_live_gate.py --live --production-shaped --gateway-url <in-cluster-core-api>/api/v1 --ani-bearer-token <redacted> --kubeconfig <in-cluster-kubeconfig> --dcgm-metrics-url <cluster-service-metrics-url> --evidence-output development-records/live-evidence/sprint13-gpu-inventory-dcgm-live-evidence.json
```

## 5. 关联文档

- Sprint 13 执行地图：[`sprint13-real-provider-readiness-plan.md`](sprint13-real-provider-readiness-plan.md)
- 当前冲刺入口：[`../CURRENT-SPRINT.md`](../CURRENT-SPRINT.md)
- Sprint 5 GPU historical evidence：[`m1-k8s-live-k-gpu-scheduling-real-lab-progress.md`](m1-k8s-live-k-gpu-scheduling-real-lab-progress.md)
- S04 A 轨记录：[`sprint13-gpu-inventory-dcgm-a-track.md`](sprint13-gpu-inventory-dcgm-a-track.md)
- 代码：`pkg/ports/gpu_inventory.go`、`pkg/adapters/runtime/local_gpu_inventory.go`、`services/ani-gateway/internal/router/gpu_inventory_resources.go`
