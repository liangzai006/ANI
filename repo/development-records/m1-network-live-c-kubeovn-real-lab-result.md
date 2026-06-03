# M1-NETWORK-LIVE-C — Kube-OVN Real Lab Live Result

完成日期：2026-06-02
对应 Sprint：Sprint 5（真实 live gate 收敛）
验证结果：`python scripts/validate_kubeovn_network_live_gate_test.py` EXIT:0；`KUBECONFIG=/Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig python scripts/validate_kubeovn_network_live_gate.py --live --evidence-output development-records/live-evidence/kubeovn-network-live-gate-2026-06-02.json` EXIT:0。

## 实现了什么

在三台物理开发服务器组成的 REAL-K8S-LAB-A 上执行了 `M1-NETWORK-LIVE-A` Kube-OVN network live gate，并归档 evidence JSON：

- `repo/development-records/live-evidence/kubeovn-network-live-gate-2026-06-02.json`

本次 live gate 证明以下资源可在真实集群创建并读回：

- Kube-OVN `Vpc`：`vpc-ani-live-net`
- Kube-OVN `Subnet`：`subnet-ani-live-subnet`
- Kubernetes `NetworkPolicy`：`sg-ani-live-sg`
- Kubernetes `Service`：`lb-ani-live-lb`
- 租户 namespace：`ani-tenant-tenant-a`

## 真实环境依赖修复

首次执行 live gate 时，真实环境暴露了两个问题：

1. `validate_kubeovn_network_live_gate.py --live` 会创建 namespaced resource，但没有先创建租户 namespace。
   - 修复：live runner 先 apply tenant `Namespace`。
   - 回归测试：`test_live_gate_creates_tenant_namespace_before_namespaced_resources`。

2. 三台服务器上的 Kube-OVN CNI 反复 `CrashLoopBackOff`。日志显示 CNI 等待 `ovn0` 网关 `100.64.0.1`，而 Kube-OVN 默认 join subnet 使用 `100.64.0.0/16`，与本环境中 Tailscale CGNAT 地址规划冲突。
   - 修复：将 Kube-OVN join subnet 从 `100.64.0.0/16` 迁移到 `172.30.0.0/16`。
   - 保持不变：Kubernetes Node Internal IP、服务器互访、OVN DB IP、apiserver 内部访问仍使用 `10.10.1.66-68`。
   - 验证：`kube-ovn-cni` DaemonSet 三节点 `1/1 Running`；三台主机 `ovn0` 分配 `172.30.0.2-4/16`；三台主机均可 ping `172.30.0.1`；到 Mac 的 Tailscale 路由仍走 `tailscale0`。

## 当前边界

本批次证明 Kube-OVN Vpc/Subnet、NetworkPolicy 和 Service/LB 对象在真实 lab 可创建、可观察，并修复了 Kube-OVN CNI join subnet 与 Tailscale 地址段冲突。

本批次执行时 Service 类型为 `LoadBalancer`，但外部地址仍为 `<pending>`；当时 `M1-NETWORK-LIVE-A` validator 的通过条件是 Service 对象可观察且类型正确，不等同于已证明裸金属外部 LB 地址分配或外部可达性。

后续 `M1-NETWORK-LIVE-D` 已在同一真实 lab 上补齐 Kube-OVN external LoadBalancer IP 可达性证明；当前外部 LB 结论以 `m1-network-live-d-kubeovn-external-lb-real-lab-result.md` 和更新后的 evidence JSON 为准。

## 关键文件改动

| 文件 | 新增/修改 | 说明 |
|---|---|---|
| `scripts/validate_kubeovn_network_live_gate.py` | 修改 | `--live` 模式先创建租户 namespace，再创建 namespaced NetworkPolicy/Service |
| `scripts/validate_kubeovn_network_live_gate_test.py` | 修改 | 增加 namespace 创建顺序回归测试 |
| `development-records/live-evidence/kubeovn-network-live-gate-2026-06-02.json` | 新增 | 真实 lab live gate evidence |
| `development-records/m1-network-live-c-kubeovn-real-lab-result.md` | 新增 | 记录真实执行结果、依赖修复和边界 |

## 验证命令

```bash
python scripts/validate_kubeovn_network_live_gate_test.py
KUBECONFIG=/Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig python scripts/validate_kubeovn_network_live_gate.py --live --evidence-output development-records/live-evidence/kubeovn-network-live-gate-2026-06-02.json
kubectl -n kube-system rollout status deployment/kube-ovn-controller --timeout=240s
kubectl -n kube-system rollout status daemonset/kube-ovn-cni --timeout=360s
kubectl -n kube-system get pods -o wide
kubectl get subnet join -o yaml
kubectl get ip node-kubercloud node-dev-phys-02 node-dev-phys-03 -o wide
```
