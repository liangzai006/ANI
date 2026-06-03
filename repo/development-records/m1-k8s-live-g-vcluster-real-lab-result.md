# M1-K8S-LIVE-G — vCluster Real Lab Live Result

完成日期：2026-06-02
对应 Sprint：Sprint 5（真实 live gate 收敛）
验证结果：`python scripts/validate_vcluster_live_gate_test.py` EXIT:0；`python scripts/validate_vcluster_live_gate.py --live --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig --namespace ani-tenant-tenant-a-vcluster --gateway-url http://127.0.0.1:8080/api/v1 --ani-bearer-token dev-token --vcluster-binary /private/tmp/vcluster-v0.34.1-darwin-arm64 --evidence-output development-records/live-evidence/vcluster-live-gate-2026-06-02.json` EXIT:0。

## 实现了什么

在 REAL-K8S-LAB-A 上执行了 `M1-K8S-LIVE-A` vCluster live gate，并归档 evidence JSON：

- `repo/development-records/live-evidence/vcluster-live-gate-2026-06-02.json`

本次 live gate 证明以下链路在真实环境可运行：

- Helm 安装/升级 vCluster release：`k8sclu-live`
- vCluster workload namespace：`ani-tenant-tenant-a-vcluster`
- vCluster pod 和 synced CoreDNS pod 进入 Running
- vCluster kubeconfig 可用，`kubectl get --raw /version` 返回 `v1.35.0`
- Core Gateway `forwarding_static` live proxy 可转发 `/version` 到真实 vCluster API，并返回 HTTP 200

## 真实环境依赖修复

首次执行 live gate 时，真实环境暴露了三个问题：

1. `validate_vcluster_live_gate.py --live` 没有把 host `KUBECONFIG` 传给 Helm/vCluster CLI。
   - 修复：新增 `--kubeconfig`，Helm 和 vCluster 命令通过环境变量继承 host kubeconfig。
   - 回归测试：`test_live_gate_passes_host_kubeconfig_to_helm_and_vcluster_commands`。

2. vCluster 部署在 `ani-tenant-tenant-a` 时继承了 Kube-OVN network live gate 的 private subnet，无法访问 Kubernetes Service IP `10.96.0.1:443`。
   - 修复：新增 `--namespace` / `ANI_LIVE_NAMESPACE`，本次 vCluster 使用独立 namespace `ani-tenant-tenant-a-vcluster`，落在默认 `ovn-default` subnet。
   - 边界：服务器间与集群内部配置仍使用 `10.10.1.66-68`；Tailscale 只用于 Mac/Codex 访问 lab。

3. 真实 lab 没有默认 StorageClass/PV，vCluster StatefulSet PVC 无法绑定。
   - 修复：新增 dev lab hostPath PV manifest `deploy/real-k8s-lab/vcluster-live-hostpath-pv.yaml`，绑定 `data-k8sclu-live-0`。
   - 边界：该 PV 是真实开发 lab 依赖，不是生产存储抽象或租户持久化方案。

## Validator 修正

本次还修正了 validator 与 vCluster CLI 行为不匹配的问题：

- `vcluster connect --print` 在当前 CLI 版本会长时间持有连接，不适合作为非交互 live gate。
- 改为 `vcluster connect ... --background-proxy=false -- kubectl get --raw /version`，直接验证生成 kubeconfig 能驱动 kubectl，并避免把 kubeconfig/token 写入 evidence。
- vCluster CLI stdout 会先打印状态行再打印 JSON，validator 现在从 stdout 中提取 Kubernetes `/version` JSON 对象。
- Core proxy 前先通过 Core API 创建 cluster 记录，再用返回的 Core cluster ID 发起 proxy；Helm release 名仍为 `k8sclu-live`。

## 当前边界

本批次证明 vCluster Helm install、kubeconfig 可用性和 Core live proxy `/version` 转发已在真实 lab 通过。

Core proxy 本次链路为 Gateway `forwarding_static` -> 本机 `kubectl proxy` -> live vCluster API。该链路证明 Gateway forwarding adapter 能对真实 vCluster API 转发并返回结果；不等同于生产已完成长期运行的 per-cluster metadata target、KMS 管理 bearer token 或直连 TLS CA 配置。

本批次不包含 vCluster upgrade live gate、Cluster API node pool live gate、GPU 调度、KMS/SM4、Kubernetes Secret 注入或 controller HA failover。

## 关键文件改动

| 文件 | 新增/修改 | 说明 |
|---|---|---|
| `scripts/validate_vcluster_live_gate.py` | 修改 | 支持 host kubeconfig、namespace override、自定义 CLI binary；改用 `vcluster connect -- kubectl /version`；新增 Core cluster register 步骤；evidence 不写 kubeconfig |
| `scripts/validate_vcluster_live_gate_test.py` | 修改 | 覆盖 host kubeconfig、namespace override、CLI stdout JSON 提取、Core cluster register 和清晰 Core proxy 网络错误 |
| `deploy/real-k8s-lab/vcluster-live-gate.yaml` | 修改 | live check 描述改为非交互 `vcluster connect -- kubectl /version`，并补充 Core cluster register |
| `deploy/real-k8s-lab/vcluster-live-hostpath-pv.yaml` | 新增 | REAL-K8S-LAB-A vCluster live gate dev hostPath PV |
| `development-records/live-evidence/vcluster-live-gate-2026-06-02.json` | 新增 | 真实 lab live gate evidence |
| `development-records/m1-k8s-live-g-vcluster-real-lab-result.md` | 新增 | 记录真实执行结果、依赖修复和边界 |

## 验证命令

```bash
python scripts/validate_vcluster_live_gate_test.py

KUBECONFIG=/Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig \
/private/tmp/vcluster-v0.34.1-darwin-arm64 connect k8sclu-live \
  --namespace ani-tenant-tenant-a-vcluster \
  --background-proxy=false \
  -- kubectl get --raw /version

KUBECONFIG=/Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig \
/private/tmp/vcluster-v0.34.1-darwin-arm64 connect k8sclu-live \
  --namespace ani-tenant-tenant-a-vcluster \
  --background-proxy=false \
  -- kubectl proxy --address=127.0.0.1 --port=18001 --accept-hosts=".*"

ANI_AUTH_MODE=dev \
K8S_CLUSTER_PROXY_MODE=forwarding_static \
K8S_CLUSTER_PROXY_TARGET_SERVER=http://127.0.0.1:18001 \
./bin/ani-gateway

python scripts/validate_vcluster_live_gate.py --live \
  --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig \
  --namespace ani-tenant-tenant-a-vcluster \
  --gateway-url http://127.0.0.1:8080/api/v1 \
  --ani-bearer-token dev-token \
  --vcluster-binary /private/tmp/vcluster-v0.34.1-darwin-arm64 \
  --evidence-output development-records/live-evidence/vcluster-live-gate-2026-06-02.json
```
