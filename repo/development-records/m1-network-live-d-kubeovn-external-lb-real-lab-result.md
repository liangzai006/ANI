# M1-NETWORK-LIVE-D — Kube-OVN External LoadBalancer Real Lab Result

完成日期：2026-06-02
对应 Sprint：Sprint 5（真实 live gate 收敛）
验证结果：`python -m unittest validate_kubeovn_network_live_gate_test.py` EXIT:0；`python scripts/validate_kubeovn_network_live_gate.py --live --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig --external-lb-live --external-lb-curl-host ANI1 --external-lb-curl-host ANI2 --external-lb-curl-host ANI3 --external-lb-reconcile-stamp 2026-06-02T15:12:00Z --evidence-output development-records/live-evidence/kubeovn-network-live-gate-2026-06-02.json` EXIT:0。

## 实现了什么

在 `M1-NETWORK-LIVE-C` 的 Kube-OVN Vpc/Subnet、NetworkPolicy 和 Service/LB resource live gate 基础上，补齐了 REAL-K8S-LAB-A 的外部 LoadBalancer IP 可达性证明。

本次 evidence 已归档到：

- `repo/development-records/live-evidence/kubeovn-network-live-gate-2026-06-02.json`

本次证明范围：

- Kube-OVN `enable-lb-svc` 真实开启。
- Multus/macvlan underlay attachment 可为 Kube-OVN LB helper 分配外部 IP。
- LB helper Pod 的 `net1` 持有外部 IP。
- LB helper Pod 中存在指向 Service ClusterIP 的 DNAT 规则和 MASQUERADE 规则。
- 三台 REAL-K8S-LAB-A 节点通过 SSH 触发 HTTP 请求，均可访问外部 LB IP 并得到 `ani-kubeovn-external-lb-ok` 响应。

## 真实环境依赖修复

真实执行暴露并修复了以下依赖问题：

1. REAL-K8S-LAB-A 初始未安装 Multus NAD CRD，Kube-OVN external LB helper 无法挂接 underlay network。
   - 修复：安装 Multus thick DaemonSet，并将内存 request/limit 调整到真实节点可稳定运行的值。

2. Kube-OVN controller 初始 `--enable-lb-svc=false`。
   - 修复：live validator 在 external LB 模式下确认并启用 `--enable-lb-svc=true`。

3. 当前节点镜像源无法拉取 `docker.io/kubeovn/vpc-nat-gateway:v1.15.8`。
   - 修复：使用节点已具备的 `docker.io/kubeovn/kube-ovn:v1.15.8` 作为 helper image，并通过 ConfigMap 挂载 Kube-OVN v1.15.8 兼容的 `lb-svc.sh`。
   - 兼容性调整：该镜像缺少 `ipcalc`，且 `arping` 参数和 stderr 行为不同于官方 `vpc-nat-gateway` 镜像；live-gate 脚本保留 EIP/DNAT 语义，同时使用该镜像支持的 `arping -S -i` 调用并静默非错误 warning。

4. underlay Subnet 必须显式开启 `enableExternalLBAddress`，否则 Service status 不会被当前 controller 路径视作属于 external LB subnet。
   - 修复：`deploy/real-k8s-lab/kubeovn-lb-external-deps.yaml` 将 `attach-subnet` 设置为 `enableExternalLBAddress: true`。

## 当前边界

本批次证明 REAL-K8S-LAB-A 上 Kube-OVN external LoadBalancer IP 的可达性。当前仍不宣称生产环境的镜像仓库、LB helper 镜像供应链、Helm/Operator 化部署或长期漂移修复已经完成。

本批次没有改变服务器之间的内部访问原则：服务器互访、Kubernetes Node Internal IP 和集群内部配置继续使用真实 LAN 地址；Tailscale 只用于本机 Codex/Mac 访问 lab 服务器和 Kubernetes API 的远程通道。

## 关键文件改动

| 文件 | 新增/修改 | 说明 |
|---|---|---|
| `deploy/real-k8s-lab/kubeovn-lb-external-deps.yaml` | 新增/修改 | 定义 external LB underlay NAD、Subnet、smoke Deployment 和 Service |
| `deploy/real-k8s-lab/kubeovn-lb-svc-script-configmap.yaml` | 新增 | 为当前可用 helper image 提供兼容的 `lb-svc.sh` |
| `deploy/real-k8s-lab/kubeovn-network-live-gate.yaml` | 修改 | 增加 external LB reachability live check |
| `scripts/validate_kubeovn_network_live_gate.py` | 修改 | 增加 `--external-lb-live` 真实验证路径和 evidence 输出 |
| `scripts/validate_kubeovn_network_live_gate_test.py` | 修改 | 增加 external LB helper patch、DNAT 和 curl evidence 回归测试 |
| `development-records/live-evidence/kubeovn-network-live-gate-2026-06-02.json` | 修改 | 增加 `external_load_balancer` 证据 |

## 验证命令

```bash
cd repo/scripts
python -m unittest validate_kubeovn_network_live_gate_test.py

cd repo
python scripts/validate_kubeovn_network_live_gate.py --live \
  --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig \
  --external-lb-live \
  --external-lb-curl-host ANI1 \
  --external-lb-curl-host ANI2 \
  --external-lb-curl-host ANI3 \
  --external-lb-reconcile-stamp 2026-06-02T15:12:00Z \
  --evidence-output development-records/live-evidence/kubeovn-network-live-gate-2026-06-02.json
```
