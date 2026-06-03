# M1-K8S-LIVE-I — Node Pool/GPU Real Lab Blocker Evidence

日期：2026-06-02
对应 Sprint：Sprint 5（真实 live gate 收敛）
验证结果：未通过。已归档阻塞证据 `development-records/live-evidence/k8s-node-pool-gpu-live-blocker-2026-06-02.json`。

## 结论

`M1-K8S-LIVE-B` / `validate-k8s-node-pool-live-gate` 当前不能在 REAL-K8S-LAB-A 上按定义证明通过：

- 集群没有 Cluster API `MachineDeployment` API resource，`machinedeployments.cluster.x-k8s.io` CRD 不存在，`capi-system` 等 Cluster API namespace 也不存在。
- 三台真实节点的 Kubernetes allocatable 均未暴露 `nvidia.com/gpu`。
- 实测创建请求 `nvidia.com/gpu: 1` 的 smoke Pod 后，Kubernetes scheduler 返回 `Insufficient nvidia.com/gpu`，Pod 未进入 `PodScheduled=True`。

因此不能把真实节点池扩缩容或 GPU 节点池真实调度标记为完成。补装 Cluster API 只能解决软件 API resource 缺口，不能解决当前物理环境缺少 GPU 的调度判据；在没有真实 GPU 节点或等价硬件资源前，不应降级为 CPU-only 或 fake GPU 通过。

2026-06-02 追加复核：已在 `M1-K8S-LIVE-J` 中把 node pool provider 渲染的 `MachineDeployment` 调整为真实 Cluster API `v1beta1` schema 合法结构，GPU/规格 intent 改由 metadata labels/annotations 保留，不再使用 CAPI 不接受的 `template.spec.gpu`。该修正只解决代码边界兼容性，不改变本记录的环境阻塞结论。

2026-06-02 追加进展：`M1-K8S-LIVE-K` 已在 ANI1 / `kubercloud`、ANI2 / `dev-phys-02`、ANI3 / `dev-phys-03` 三台服务器上完成 NVIDIA driver、NVIDIA Container Toolkit 和 NVIDIA device plugin 部署，三个 Kubernetes Node 均已暴露 `nvidia.com/gpu: 2`。通用 GPU smoke Pod 与固定到 control-plane 节点的 `ani-node-pool-gpu-smoke-ani1` 均已进入 `Ready=True` 并在容器内成功运行 `nvidia-smi`。因此本记录中的 GPU 调度阻塞已解除；剩余阻塞收敛为 Cluster API `MachineDeployment` API resource 与兼容基础设施 provider 缺失。新证据见 `development-records/live-evidence/k8s-node-pool-gpu-scheduling-live-progress-2026-06-02.json`。

2026-06-02 追加代码进展：`M1-K8S-LIVE-L` 已解除 node pool provider 固定渲染 `ANIMachineTemplate` 的代码阻塞。Gateway 现在可通过环境变量配置 CAPK `KubeadmConfigTemplate` / `KubevirtMachineTemplate` refs 与 machine version。该修正仍不代表 `M1-K8S-LIVE-B` 完整通过；真实 lab 复核仍显示 Cluster API CRD 与 `clusterctl` 未安装，后续仍需完成 CAPI/CAPK 真实安装与 provider-backed create/scale 验证。

## 已执行检查

```bash
kubectl --kubeconfig local-secrets/real-k8s-lab.kubeconfig get crd machinedeployments.cluster.x-k8s.io
kubectl --kubeconfig local-secrets/real-k8s-lab.kubeconfig get ns capi-system capi-kubeadm-bootstrap-system capi-kubeadm-control-plane-system
kubectl --kubeconfig local-secrets/real-k8s-lab.kubeconfig get nodes -o 'custom-columns=NAME:.metadata.name,CPU:.status.allocatable.cpu,MEMORY:.status.allocatable.memory,GPU:.status.allocatable.nvidia\.com/gpu'
kubectl --kubeconfig local-secrets/real-k8s-lab.kubeconfig -n ani-tenant-tenant-a run ani-node-pool-gpu-smoke-blocker --image=nvidia/cuda:12.4.1-base-ubuntu22.04 --restart=Never --overrides='<gpu request redacted for brevity>'
kubectl --kubeconfig local-secrets/real-k8s-lab.kubeconfig -n ani-tenant-tenant-a wait --for=condition=PodScheduled pod/ani-node-pool-gpu-smoke-blocker --timeout=20s
kubectl --kubeconfig local-secrets/real-k8s-lab.kubeconfig -n ani-tenant-tenant-a delete pod ani-node-pool-gpu-smoke-blocker --ignore-not-found=true
```

## 当前边界

这条记录不是通过记录，也不改变 `M1-K8S-LIVE-B` 的完成判据。Sprint 5 仍处于收敛中，node pool/GPU live gate 仍未完成。

恢复推进时，必须先满足两类真实依赖：

1. 安装并配置 Cluster API 及能管理当前真实节点池形态的对应基础设施 provider；仅安装 CAPI core CRD 不足以证明真实扩缩容。
2. GPU 依赖已由 `M1-K8S-LIVE-K` 解除；后续回归仍需保留 `nvidia.com/gpu` allocatable 与 GPU smoke Pod 调度检查。

Tailscale 仍仅用于 Mac/Codex 访问真实 lab；服务器之间和集群内部配置继续使用 `10.10.1.66-68`。
