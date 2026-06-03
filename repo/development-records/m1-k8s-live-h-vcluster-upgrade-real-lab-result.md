# M1-K8S-LIVE-H — vCluster Upgrade Real Lab Live Result

完成日期：2026-06-02
对应 Sprint：Sprint 5（真实 live gate 收敛）
验证结果：`make validate-vcluster-upgrade-live-gate` EXIT:0；`python scripts/validate_vcluster_upgrade_live_gate.py --live --tenant-id tenant-a-vcluster-upgrade --cluster-id k8sclu-upgrade-live --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig --gateway-url http://127.0.0.1:8080/api/v1 --ani-bearer-token dev-token --initial-version v1.35.0 --target-version v1.35.0 --vcluster-binary /private/tmp/vcluster-v0.34.1-darwin-arm64 --local-proxy-port 18002 --evidence-output development-records/live-evidence/vcluster-upgrade-live-gate-2026-06-02.json` EXIT:0。

## 实现了什么

在 REAL-K8S-LAB-A 上执行了 `M1-K8S-LIVE-C` vCluster upgrade live gate，并归档 evidence JSON：

- `repo/development-records/live-evidence/vcluster-upgrade-live-gate-2026-06-02.json`

本次 live gate 证明以下链路在真实环境可运行：

- Core API 创建 provider-backed vCluster 集群记录
- Gateway `vcluster_helm` provider 通过 Helm 管理真实 vCluster release
- validator 为真实 lab 生成并绑定 dev hostPath PV，解决无默认 StorageClass/PV 的 lab 前置
- Core upgrade API 调用 vCluster Helm upgrade，Helm values 中 `controlPlane.distro.k8s.version` 与目标版本一致
- 升级后通过 `vcluster connect -- kubectl get --raw /version` 验证租户 vCluster API 返回 `v1.35.0`
- Core Gateway `forwarding_static` live proxy 可转发 `/version` 到升级后的真实 vCluster API，并返回 HTTP 200

## 真实环境依赖修复

本次真实执行暴露并修正了 upgrade live gate 的运行假设：

1. Gateway vCluster Helm provider 仍使用旧 chart key `sync.toHost.service.enabled=true`。
   - 修复：改为当前 vCluster chart 接受的 `sync.toHost.services.enabled=true`。
   - 回归测试：`TestVClusterHelmProviderAdapterRunsHelmUpgradeInstall` 与 `TestVClusterHelmProviderAdapterRunsHelmUpgradeForClusterVersion`。

2. upgrade validator 假设已有固定 Core cluster ID，并使用 `vcluster connect --print`。
   - 修复：live 模式先通过 Core API 创建 provider-backed cluster，随后使用返回的 Core cluster ID 执行 upgrade、Helm values、vCluster connect 和 Core proxy。
   - 修复：改为非交互 `vcluster connect ... --background-proxy=false -- kubectl get --raw /version`，避免把 kubeconfig/token 写入 evidence。

3. 真实 lab 没有默认 StorageClass/PV。
   - 修复：validator 基于 Core cluster ID 生成临时 hostPath PV manifest，并通过 host kubeconfig `kubectl apply` 绑定 `data-<core_cluster_id>-0` PVC。
   - 边界：该 PV 是真实开发 lab 依赖，不是生产存储抽象或租户持久化方案。

4. Core proxy 需要一个可访问的升级后 vCluster API 目标。
   - 修复：validator 在本机通过 vCluster CLI 启动 `kubectl proxy`，Gateway 使用 `forwarding_static` 指向该本机代理，再通过 Core proxy API 验证 `/version`。

## 当前边界

本批次证明 vCluster upgrade live gate 已在真实 lab 通过，且升级后 kubeconfig/API 访问和 Core live proxy `/version` 仍可用。

本次目标版本为 `v1.35.0`，原因是当前 vCluster chart 默认 Kubernetes 版本为 `v1.35.0`，且 chart 明确 `controlPlane.distro` 部署后不可随意切换；本批次验证 Helm upgrade intent、目标版本 values 和升级后 API 可用性，不宣称跨小版本真实升级策略已经生产化。

Core proxy 本次链路为 Gateway `forwarding_static` -> 本机 `kubectl proxy` -> live vCluster API。该链路证明 Gateway forwarding adapter 能对升级后的真实 vCluster API 转发并返回结果；不等同于生产已完成长期运行的 per-cluster metadata target、KMS 管理 bearer token 或直连 TLS CA 配置。

Tailscale 仍仅用于 Mac/Codex 访问真实 lab；服务器之间和集群内部配置继续使用 `10.10.1.66-68`。

本批次不包含 Cluster API node pool live gate、GPU 调度、KMS/SM4、Kubernetes Secret 注入或 controller HA failover。

## 关键文件改动

| 文件 | 新增/修改 | 说明 |
|---|---|---|
| `pkg/adapters/runtime/vcluster_helm_provider.go` | 修改 | vCluster chart service sync key 改为 `sync.toHost.services.enabled=true` |
| `pkg/adapters/runtime/vcluster_helm_provider_test.go` | 修改 | 覆盖 Apply/Upgrade 使用当前 chart key |
| `scripts/validate_vcluster_upgrade_live_gate.py` | 修改 | live 模式支持 Core create、host kubeconfig、dev hostPath PV、非交互 vCluster connect、本机 proxy 和无敏感 evidence |
| `scripts/validate_vcluster_upgrade_live_gate_test.py` | 修改 | 覆盖 Core create -> PV -> upgrade -> Helm values -> vCluster `/version` -> Core proxy 顺序 |
| `deploy/real-k8s-lab/vcluster-upgrade-live-gate.yaml` | 修改 | live checks 对齐真实 Core cluster ID、dev hostPath PV、非交互 vCluster connect 与本机 proxy |
| `development-records/live-evidence/vcluster-upgrade-live-gate-2026-06-02.json` | 新增 | 真实 lab upgrade live gate evidence |
| `development-records/m1-k8s-live-h-vcluster-upgrade-real-lab-result.md` | 新增 | 记录真实执行结果、依赖修复和边界 |

## 验证命令

```bash
make validate-vcluster-upgrade-live-gate

ANI_AUTH_MODE=dev \
KUBECONFIG=/Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig \
K8S_CLUSTER_PROVIDER_MODE=vcluster_helm \
K8S_CLUSTER_PROXY_MODE=forwarding_static \
K8S_CLUSTER_PROXY_TARGET_SERVER=http://127.0.0.1:18002 \
VCLUSTER_BINARY=/private/tmp/vcluster-v0.34.1-darwin-arm64 \
./bin/ani-gateway

python scripts/validate_vcluster_upgrade_live_gate.py --live \
  --tenant-id tenant-a-vcluster-upgrade \
  --cluster-id k8sclu-upgrade-live \
  --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig \
  --gateway-url http://127.0.0.1:8080/api/v1 \
  --ani-bearer-token dev-token \
  --initial-version v1.35.0 \
  --target-version v1.35.0 \
  --vcluster-binary /private/tmp/vcluster-v0.34.1-darwin-arm64 \
  --local-proxy-port 18002 \
  --evidence-output development-records/live-evidence/vcluster-upgrade-live-gate-2026-06-02.json
```
