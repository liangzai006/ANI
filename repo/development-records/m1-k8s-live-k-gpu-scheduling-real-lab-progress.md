# M1-K8S-LIVE-K — GPU Scheduling Real Lab Progress

日期：2026-06-02
对应 Sprint：Sprint 5（真实 live gate 收敛）
验证结果：部分推进。GPU 调度依赖已解除；`M1-K8S-LIVE-B` 完整 node pool live gate 仍未通过。

Evidence：`development-records/live-evidence/k8s-node-pool-gpu-scheduling-live-progress-2026-06-02.json`

## 结论

REAL-K8S-LAB-A 中三台物理服务器均已真实暴露 NVIDIA GPU 资源：

- ANI1 / `kubercloud`、ANI2 / `dev-phys-02`、ANI3 / `dev-phys-03` 均已加载 NVIDIA driver，`nvidia-smi -L` 可见每台 2 张 NVIDIA GeForce RTX 4090。
- 三台服务器均已安装 NVIDIA Container Toolkit `1.19.1`，containerd 已配置 `nvidia` runtime。
- `kube-system/nvidia-device-plugin-daemonset` 使用 `nvcr.io/nvidia/k8s-device-plugin:v0.19.2`，通过 `ani.dev/gpu=nvidia` nodeSelector 部署到三台 GPU 节点；control-plane 节点额外通过 `node-role.kubernetes.io/control-plane:NoSchedule` toleration 覆盖。
- 三个 Kubernetes Node `capacity` / `allocatable` 均已上报 `nvidia.com/gpu: 2`。
- `ani-tenant-tenant-a/ani-node-pool-gpu-smoke` 请求 `nvidia.com/gpu: 1`，已进入 `PodScheduled=True` 和 `Running`，容器内 `nvidia-smi` 成功输出 driver/CUDA/GPU 信息。
- `ani-tenant-tenant-a/ani-node-pool-gpu-smoke-ani1` 固定到 `kubercloud`，已进入 `Ready=True` 和 `Running`，证明 control-plane 节点上的 GPU 容器也可运行。

因此，`M1-K8S-LIVE-I` 中的 GPU 调度阻塞已经解除。

## 仍未完成

`M1-K8S-LIVE-B` 完整 gate 仍不能标记通过：

- 当前集群仍没有 `machinedeployments.cluster.x-k8s.io` 等 Cluster API CRD。
- 控制面节点未安装 `clusterctl`。
- 当前 Core node pool provider 生成的 `MachineDeployment.spec.template.spec.infrastructureRef.kind` 是 `ANIMachineTemplate`，但真实 lab 中没有对应 CRD 或基础设施 provider。

只安装 CAPI core CRD 最多能让 `MachineDeployment` 对象被 API server 接受，不能证明真实节点池扩缩容。恢复推进时必须选择并接入一个真实基础设施 provider，或先把 Core provider 的 infrastructureRef 设计调整到可配置并与所选 provider 对齐。

## 已执行检查摘要

```bash
kubectl -n kube-system rollout status ds/nvidia-device-plugin-daemonset --timeout=180s
kubectl describe node kubercloud
kubectl describe node dev-phys-02
kubectl describe node dev-phys-03
kubectl -n ani-tenant-tenant-a apply -f ani-gpu-smoke.yml
kubectl -n ani-tenant-tenant-a wait --for=condition=PodScheduled pod/ani-node-pool-gpu-smoke --timeout=180s
kubectl -n ani-tenant-tenant-a wait --for=condition=Ready pod/ani-node-pool-gpu-smoke --timeout=300s
kubectl -n ani-tenant-tenant-a logs ani-node-pool-gpu-smoke
kubectl -n ani-tenant-tenant-a apply -f ani-gpu-smoke-ani1.yml
kubectl -n ani-tenant-tenant-a wait --for=condition=Ready pod/ani-node-pool-gpu-smoke-ani1 --timeout=300s
kubectl -n ani-tenant-tenant-a logs ani-node-pool-gpu-smoke-ani1
kubectl get crd
command -v clusterctl
```

## 当前边界

本记录只证明 GPU runtime/device-plugin/scheduler 依赖已可用，不证明 node pool provider-backed create/update 已完成。Sprint 5 仍需完成 Cluster API / infrastructure provider 侧真实验证。

Tailscale 仍仅用于 Mac/Codex 访问真实 lab；服务器之间和集群内部配置继续使用真实 LAN 地址。
