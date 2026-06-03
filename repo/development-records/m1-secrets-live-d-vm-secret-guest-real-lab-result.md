# M1-SECRETS-LIVE-D — VM Secret Guest Real Lab Result

完成日期：2026-06-02
对应 Sprint：Sprint 5（真实 live gate 收敛）
验证结果：`python scripts/validate_secrets_live_gate.py --live --tenant-id tenant-a --gateway-url http://127.0.0.1:8080/api/v1 --ani-bearer-token dev-token --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig --evidence-output development-records/live-evidence/secrets-live-gate-2026-06-02.json` EXIT:0。

## 实现了什么

在 `M1-SECRETS-LIVE-A` / `validate-secrets-live-gate` 的既有 Secret live gate 上补强 VM 侧真实检查：

- KubeVirt `VirtualMachine` 不再只做 Secret volume/disk manifest server-side dry-run。
- live 模式会启动一个短生命周期 VM，将 Kubernetes Secret 作为 KubeVirt `secret` volume/disk 挂入 guest。
- cloud-init guest probe 在 VM 内扫描并挂载 Secret disk，串口日志确认 `password` 与 `token` 文件可读。
- validator 读取 virt-launcher 串口日志做断言，验证完成后删除 VM/VMI/launcher Pod。

本次归档 evidence：

- `repo/development-records/live-evidence/secrets-live-gate-2026-06-02.json`

Evidence 只记录 `guest_secret_volume_visible`、virt-launcher Pod 名称、运行节点和 Secret disk label，不记录 Secret 明文、bearer token 或 kubeconfig 内容。

## 真实环境结果

本次真实执行证明以下链路成立：

- Core Gateway `SECRET_PROVIDER_MODE=kubernetes_rest` 仍能写入真实 Kubernetes Secret。
- Pod env/file Secret 可见性仍通过。
- KubeVirt VM Secret volume/disk manifest 仍被 API server 接受。
- VM guest 内可挂载 label 为 `ANISECRET` 的 Secret disk，并读取 Secret 中的 `password` / `token` 文件。

本次 VM guest probe 运行在真实 lab 的 KubeVirt `v1.8.2` 环境中；evidence 显示 launcher Pod 调度到真实节点 `dev-phys-03`。

## 当前边界

本批次证明 KubeVirt VM guest 内读取 Secret volume 的真实执行结果已经通过。

Gateway 本次仍通过本机 `kubectl proxy` 访问真实 Kubernetes API，这是当前 live gate 验证链路，不代表生产 Kubernetes API CA/client credential 管理已经完成。

本批次不改变 KubeVirt console/VNC 的边界；后续 `M1-KUBEVIRT-LIVE-D` 已单独补齐 console/VNC WebSocket session 真实建立证据。

Tailscale 仅用于 Mac/Codex 访问真实 lab；服务器之间和集群内部配置继续使用 `10.10.1.66-68` 所在 LAN 地址。

## 关键文件改动

| 文件 | 新增/修改 | 说明 |
|---|---|---|
| `scripts/validate_secrets_live_gate.py` | 修改 | live 模式新增 VM guest Secret probe、virt-launcher 日志断言和 VM 清理 |
| `scripts/validate_secrets_live_gate_test.py` | 修改 | 覆盖 guest probe manifest、VMI Ready、virt-launcher pod 查询和串口日志 marker |
| `deploy/real-k8s-lab/secrets-live-gate.yaml` | 修改 | 新增 `kubevirt-vm-secret-volume-guest-visible` live check |
| `development-records/live-evidence/secrets-live-gate-2026-06-02.json` | 修改 | evidence 增加 `vm_guest_secret` 结果对象，不含 Secret 明文 |
| `development-records/m1-secrets-live-d-vm-secret-guest-real-lab-result.md` | 新增 | 记录 VM guest Secret volume 真实可见性结果 |

## 验证命令

```bash
python -m unittest validate_secrets_live_gate_test.py
python scripts/validate_secrets_live_gate.py

KUBECONFIG=/Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig \
kubectl proxy --address=127.0.0.1 --port=18003 --accept-hosts='.*'

ANI_AUTH_MODE=dev \
SECRET_PROVIDER_MODE=kubernetes_rest \
KUBERNETES_API_HOST=http://127.0.0.1:18003 \
KUBERNETES_PROVIDER_FIELD_MANAGER=ani-secret-live-gate \
./bin/ani-gateway

python scripts/validate_secrets_live_gate.py --live \
  --tenant-id tenant-a \
  --gateway-url http://127.0.0.1:8080/api/v1 \
  --ani-bearer-token dev-token \
  --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig \
  --evidence-output development-records/live-evidence/secrets-live-gate-2026-06-02.json
```
