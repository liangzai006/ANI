# M1-RECONCILE-LIVE-C — Controller HA Real Lab Live Result

完成日期：2026-06-02
对应 Sprint：Sprint 5（真实 live gate 收敛）
验证结果：`make validate-reconcile-ha-live-gate` EXIT:0；`python scripts/validate_reconcile_ha_live_gate.py --live --database-url ... --namespace ani-system --worker-selector app=ani-reconcile-worker --metrics-url kubernetes-raw --metrics-kubectl-raw-path /api/v1/namespaces/ani-system/services/ani-reconcile-worker-metrics:9205/proxy/metrics --psql-kubectl-namespace ani-system --psql-kubectl-selector app=ani-reconcile-ha-postgres --evidence-output development-records/live-evidence/reconcile-ha-live-gate-2026-06-02.json` EXIT:0。

## 实现了什么

在 REAL-K8S-LAB-A 上执行了 `M1-RECONCILE-LIVE-A` Controller HA live gate，并归档 evidence JSON：

- `repo/development-records/live-evidence/reconcile-ha-live-gate-2026-06-02.json`

本次 live gate 证明以下链路在真实环境可运行：

- 两个真实 Kubernetes Pod 运行 `services/reconcile-worker` 独立 worker 进程
- worker 通过真实 Postgres `control_plane_leases` 表执行 metadata-backed leader election
- worker metrics 通过 Kubernetes API service proxy 暴露 Prometheus text counters
- validator 删除 active leader Pod 后，follower 成为新的 lease holder
- 删除 leader 后 Deployment 重新拉起 replacement Pod，两个 worker 最终恢复 Running

## 真实环境依赖修复

首次推进 Controller HA live gate 时，真实环境暴露了两个执行缺口：

1. Mac 本机没有 `psql`，而 live gate 需要查询真实 `control_plane_leases`。
   - 修复：`validate_reconcile_ha_live_gate.py` 支持 `--psql-kubectl-namespace` / `--psql-kubectl-selector`，通过 `kubectl exec` 到真实 Postgres Pod 执行同一条 lease SQL。
   - 回归测试：`test_live_runner_can_query_lease_through_kubectl_exec_psql`。

2. `kubectl custom-columns` 读取带 `/` 的 `ani.kubercloud.io/reconcile-identity` label 时返回 `<none>`。
   - 修复：validator 改为 `kubectl get pods -o json` 后用 Python 解析 label。
   - 回归测试：`test_live_gate_observes_lease_deletes_leader_and_confirms_failover` 覆盖 JSON pod list。

3. 本机 `kubectl port-forward` 容易在 leader Pod 删除或 service endpoint 变化时丢失目标。
   - 修复：`validate_reconcile_ha_live_gate.py` 支持 `--metrics-kubectl-raw-path`，通过 Kubernetes API service proxy 读取 metrics，不需要后台 port-forward 进程。
   - 回归测试：`test_live_gate_can_fetch_metrics_through_kubectl_raw_service_proxy`。

## 当前边界

本批次证明 controller 多副本 HA failover、metadata-backed lease holder 切换和 metrics 检查已在真实 lab 通过。

本次为 live gate 部署了最小验证依赖：Postgres、NATS、Redis、两个 reconcile worker Deployment、metrics Service，以及三台物理服务器上的 hostPath worker 二进制。该部署用于 REAL-K8S-LAB-A 验证，不等同于生产 Helm/Operator 化控制面部署。

本次 metrics 通过 Kubernetes API service proxy 读取，避免本机 port-forward 进程残留；evidence 不包含数据库连接串、密码、token 或 kubeconfig 内容。

Tailscale 仍仅用于 Mac/Codex 访问真实 lab；服务器之间和集群内部配置继续使用 `10.10.1.66-68` 或 Kubernetes Service DNS。

## 关键文件改动

| 文件 | 新增/修改 | 说明 |
|---|---|---|
| `deploy/real-k8s-lab/reconcile-ha-live-deps.yaml` | 新增 | REAL-K8S-LAB-A Controller HA live gate 最小依赖与 worker 部署 |
| `scripts/validate_reconcile_ha_live_gate.py` | 修改 | 支持 kubectl exec psql、JSON label 解析和 Kubernetes API service proxy metrics |
| `scripts/validate_reconcile_ha_live_gate_test.py` | 修改 | 覆盖真实环境暴露的 psql、label 和 metrics proxy 执行路径 |
| `development-records/live-evidence/reconcile-ha-live-gate-2026-06-02.json` | 新增 | 真实 lab Controller HA live gate evidence |
| `development-records/m1-reconcile-live-c-ha-real-lab-result.md` | 新增 | 记录真实执行结果、依赖修复和边界 |

## 验证命令

```bash
make validate-reconcile-ha-live-gate

PYTHONPATH=scripts \
python -m unittest scripts/validate_reconcile_ha_live_gate_test.py

KUBECONFIG=/Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig \
python scripts/validate_reconcile_ha_live_gate.py --live \
  --database-url 'postgres://ani:ani_dev_password@ani-reconcile-ha-postgres.ani-system.svc.cluster.local:5432/ani?sslmode=disable' \
  --namespace ani-system \
  --worker-selector app=ani-reconcile-worker \
  --metrics-url kubernetes-raw \
  --metrics-kubectl-raw-path /api/v1/namespaces/ani-system/services/ani-reconcile-worker-metrics:9205/proxy/metrics \
  --psql-kubectl-namespace ani-system \
  --psql-kubectl-selector app=ani-reconcile-ha-postgres \
  --evidence-output development-records/live-evidence/reconcile-ha-live-gate-2026-06-02.json
```
