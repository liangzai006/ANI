# M1-KUBEVIRT-LIVE-C — KubeVirt VM Real Lab Live Result

完成日期：2026-06-02
对应 Sprint：Sprint 5（真实 live gate 收敛）
验证结果：`python scripts/validate_kubevirt_vm_live_gate_test.py` EXIT:0；`python scripts/validate_kubevirt_vm_live_gate.py --live --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig --namespace ani-tenant-tenant-a --container-disk-image quay.io/kubevirt/cirros-container-disk-demo:v1.8.2 --evidence-output development-records/live-evidence/kubevirt-vm-live-gate-2026-06-02.json` EXIT:0。

## 实现了什么

在三台物理开发服务器组成的 REAL-K8S-LAB-A 上执行了 `M1-KUBEVIRT-LIVE-A` KubeVirt VM live gate，并归档 evidence JSON：

- `repo/development-records/live-evidence/kubevirt-vm-live-gate-2026-06-02.json`

本次 live gate 证明以下能力在真实集群可运行：

- KubeVirt CRD 与 KubeVirt control plane 可用。
- `VirtualMachine` 可创建、启动并观察到对应 `VirtualMachineInstance` Running/Ready。
- VNC 与 console subresource 可达；真实 API 返回 WebSocket upgrade 要求。
- VM 可停止，VMI 可删除，VM 对象最终清理干净。

## 真实环境依赖修复

首次使用默认 `quay.io/containerdisks/cirros:latest` 镜像执行时，真实环境经由当前镜像 mirror 拉取失败，VMI 停留在 `ImagePullBackOff`。本批次改用与当前 KubeVirt 版本匹配且真实环境可拉取的 `quay.io/kubevirt/cirros-container-disk-demo:v1.8.2`。

第二次执行时 VM/VMI 已成功运行，但原 validator 使用普通 `kubectl get --raw` 访问 VNC/console 子资源，并把 KubeVirt 返回的 WebSocket upgrade 要求误判为失败。当时该响应用于证明子资源存在且要求正确的 WebSocket 协议握手；后续 `M1-KUBEVIRT-LIVE-D` 已把当前 validator 升级为真实 WebSocket session probe。

## 当前边界

本批次证明 KubeVirt VM create/start/observe/stop/delete 生命周期在真实 lab 可运行，并证明 VNC/console subresource 可达且按 KubeVirt 协议要求 WebSocket upgrade。

当前不宣称已经建立交互式 console 或 VNC 会话；后续 `M1-KUBEVIRT-LIVE-D` 已用 WebSocket client 补齐真实 session 建立证据。

## 关键文件改动

| 文件 | 新增/修改 | 说明 |
|---|---|---|
| `scripts/validate_kubevirt_vm_live_gate.py` | 修改 | 识别 KubeVirt VNC/console subresource 的 WebSocket upgrade 要求，并写入 evidence |
| `scripts/validate_kubevirt_vm_live_gate_test.py` | 修改 | 增加 subresource WebSocket upgrade 响应的回归测试 |
| `development-records/live-evidence/kubevirt-vm-live-gate-2026-06-02.json` | 新增 | 真实 lab live gate evidence |
| `development-records/m1-kubevirt-live-c-vm-real-lab-result.md` | 新增 | 记录真实执行结果、依赖修复和边界 |

## 验证命令

```bash
python scripts/validate_kubevirt_vm_live_gate_test.py
python scripts/validate_kubevirt_vm_live_gate.py --live --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig --namespace ani-tenant-tenant-a --container-disk-image quay.io/kubevirt/cirros-container-disk-demo:v1.8.2 --evidence-output development-records/live-evidence/kubevirt-vm-live-gate-2026-06-02.json
kubectl --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig -n ani-tenant-tenant-a get vm,vmi,pod -o wide
```
