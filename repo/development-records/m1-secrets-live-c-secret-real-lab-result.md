# M1-SECRETS-LIVE-C — Secret Real Lab Live Result

完成日期：2026-06-02
对应 Sprint：Sprint 5（真实 live gate 收敛）
验证结果：`make validate-secrets-live-gate` EXIT:0；`python scripts/validate_secrets_live_gate.py --live --tenant-id tenant-a --gateway-url http://127.0.0.1:8080/api/v1 --ani-bearer-token dev-token --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig --evidence-output development-records/live-evidence/secrets-live-gate-2026-06-02.json` EXIT:0。

## 实现了什么

在 REAL-K8S-LAB-A 上执行了 `M1-SECRETS-LIVE-A` Secret live gate，并归档 evidence JSON：

- `repo/development-records/live-evidence/secrets-live-gate-2026-06-02.json`

本次 live gate 证明以下链路在真实环境可运行：

- Core Gateway `SECRET_PROVIDER_MODE=kubernetes_rest` 能通过 Kubernetes REST client 写入真实 Kubernetes Secret
- Core Secret binding API 可创建 env 和 file binding 记录
- `kubectl get secret` 能读取到 provider 写入的 Secret，且 `password` / `token` data 与 Core 请求一致
- 真实 Pod 通过 `envFrom.secretRef` 读取 env Secret 值
- 真实 Pod 通过 Secret volume mount 读取 file Secret 值
- KubeVirt VM Secret volume/disk manifest 通过 API server `--dry-run=server` 校验

## 真实环境依赖修复

首次执行 live gate 时，真实环境暴露了两个 validator 缺口：

1. `validate_secrets_live_gate.py --live --tenant-id tenant-a` 没有把租户上下文传给 Core API。
   - 现象：Gateway 使用 dev 默认租户，Secret provider 试图写入 `ani-tenant-00000000-0000-0000-0000-000000000001`，该 namespace 不存在。
   - 修复：`LiveRunner.post_json` 支持 `x-dev-tenant-id`，Secret create/bind 请求传入 `config.tenant_id`。
   - 回归测试：`test_live_gate_runs_core_secret_write_pod_env_file_and_vm_volume_checks` 覆盖 create/bind 请求的 tenant 传递。

2. VM Secret volume manifest 在 KubeVirt disk 上设置了非法字段 `readOnly`。
   - 现象：KubeVirt API strict decode 拒绝 `spec.template.spec.domain.devices.disks[1].readOnly`。
   - 修复：移除 disk 上的 `readOnly` 字段，保留 Secret volume 引用。
   - 回归测试：`test_vm_secret_manifest_uses_kubevirt_disk_schema_without_read_only_field`。

## 当前边界

本批次证明 Kubernetes Secret provider 写入、Pod env/file 可见性和 KubeVirt VM Secret volume manifest API 接受已在真实 lab 通过。

Gateway 本次通过本机 `kubectl proxy` 访问真实 Kubernetes API，这是因为当前 Kubernetes REST client 不直接消费 kubeconfig client certificate；该链路用于 live gate 验证，不代表生产已完成长期运行的 Kubernetes API CA/client credential 管理。

本批次不把 Secret 明文写入 evidence，不记录 bearer token 或 kubeconfig 内容。

后续 `M1-SECRETS-LIVE-D` 已在同一 live gate 上补强 VM guest probe，证明 KubeVirt VM guest 内可读取 Secret volume 内容。本批次自身完成时，VM 部分只证明 API server 接受 VM Secret volume/disk manifest。

Tailscale 仍仅用于 Mac/Codex 访问真实 lab；服务器之间和集群内部配置继续使用 `10.10.1.66-68`。

## 关键文件改动

| 文件 | 新增/修改 | 说明 |
|---|---|---|
| `scripts/validate_secrets_live_gate.py` | 修改 | Core API 请求传递 `x-dev-tenant-id`；VM Secret disk manifest 移除非法 `readOnly` 字段 |
| `scripts/validate_secrets_live_gate_test.py` | 修改 | 覆盖 tenant header 传递和 KubeVirt disk schema |
| `development-records/live-evidence/secrets-live-gate-2026-06-02.json` | 新增 | 真实 lab Secret live gate evidence；不含 Secret 明文 |
| `development-records/m1-secrets-live-c-secret-real-lab-result.md` | 新增 | 记录真实执行结果、依赖修复和边界 |

## 验证命令

```bash
make validate-secrets-live-gate

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
