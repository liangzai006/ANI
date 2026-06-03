# M1-KUBEVIRT-LIVE-D — KubeVirt Console/VNC WebSocket Session Real Lab Result

完成日期：2026-06-02
对应 Sprint：Sprint 5（真实 live gate 收敛）
验证结果：`python -m unittest validate_kubevirt_vm_live_gate_test.py` EXIT:0；`make validate-kubevirt-vm-live-gate` EXIT:0；`python scripts/validate_kubevirt_vm_live_gate.py --live --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig --namespace ani-tenant-tenant-a --container-disk-image quay.io/kubevirt/cirros-container-disk-demo:v1.8.2 --evidence-output development-records/live-evidence/kubevirt-vm-live-gate-2026-06-02.json` EXIT:0。

## 实现了什么

在 `M1-KUBEVIRT-LIVE-C` 已证明 KubeVirt VM lifecycle 和 console/VNC subresource 可达的基础上，本批次将 `validate_kubevirt_vm_live_gate.py --live` 的 console/VNC 检查升级为真实 WebSocket 会话验证。

本次验证脚本按 KubeVirt `v1.8.2` 官方 client-go subresource 行为建立连接：

- 对 console 与 VNC subresource 发起 WebSocket GET。
- 使用 KubeVirt plain stream 子协议 `plain.kubevirt.io`。
- 断言服务端返回 HTTP `101` upgrade，并回选相同子协议。
- 对 console 发送一个换行字节，确认流式会话可写。
- 对 console/VNC 读取流数据字节，证明不是普通 HTTP 可达性检查。
- 在 `finally` 中停止并删除 VM，避免失败时留下运行中 VMI。

## Evidence

真实 lab evidence 已归档：

- `repo/development-records/live-evidence/kubevirt-vm-live-gate-2026-06-02.json`

当前 evidence 中 console 与 VNC 均满足：

- `websocket_session_established: true`
- `http_status: 101`
- `subprotocol: plain.kubevirt.io`
- `received_bytes > 0`

本 evidence 不包含 kubeconfig、client certificate、client key、bearer token 或真实服务器凭据。

## 当前边界

本批次证明 KubeVirt console/VNC WebSocket session 已在 REAL-K8S-LAB-A 真实建立，并可进行基础流式读写。

本批次不宣称生产 console/VNC 访问 URL、会话租户授权、浏览器端 VNC UI、审计、连接复用或 per-cluster credential 管理已经生产化；这些仍属于后续产品化边界。

## 关键文件改动

| 文件 | 新增/修改 | 说明 |
|---|---|---|
| `scripts/validate_kubevirt_vm_live_gate.py` | 修改 | 使用标准库实现 KubeVirt console/VNC WebSocket session probe，并确保 live VM cleanup |
| `scripts/validate_kubevirt_vm_live_gate_test.py` | 修改 | 增加 WebSocket session evidence 与失败 cleanup 的单元测试 |
| `deploy/real-k8s-lab/kubevirt-vm-live-gate.yaml` | 修改 | 将 console/VNC pass condition 升级为 WebSocket session established |
| `development-records/live-evidence/kubevirt-vm-live-gate-2026-06-02.json` | 修改 | 真实 lab evidence 记录 console/VNC HTTP 101、子协议和流数据字节 |

## 验证命令

```bash
python -m unittest validate_kubevirt_vm_live_gate_test.py
make validate-kubevirt-vm-live-gate
python scripts/validate_yaml.py deploy/real-k8s-lab/kubevirt-vm-live-gate.yaml
python scripts/validate_kubevirt_vm_live_gate.py --live --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig --namespace ani-tenant-tenant-a --container-disk-image quay.io/kubevirt/cirros-container-disk-demo:v1.8.2 --evidence-output development-records/live-evidence/kubevirt-vm-live-gate-2026-06-02.json
kubectl --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig -n ani-tenant-tenant-a get vm,vmi,pod -l ani.kubercloud.io/live-gate=m1-kubevirt-live-a
```
