# SPRINT14-CORE-RESILIENCE-LIVE-GATE · Sprint14 resilience live gate

> 分支：`feature/sprint14-core-resilience-semantics`
> 状态：live gate passed；隔离 Sprint14 Core resilience fixture 范围内 production-ready
> 隔离 namespace：`ani-sprint14-resilience`
> Evidence：`development-records/live-evidence/sprint14-resilience-live-evidence.json`

## 关联文档与对照关系

| 文档 | 关系 |
|---|---|
| [`sprint14-core-resilience-plan.md`](sprint14-core-resilience-plan.md) | Sprint14 主计划；定义 P0/P1/P2 范围、未完成边界和退出标准 |
| [`README.md`](README.md) | development records 索引；本记录在 Sprint 14 Planning / Execution 表中登记 |
| [`../CURRENT-SPRINT.md`](../CURRENT-SPRINT.md) | 当前 Sprint 入口；列出本 gate 的复跑命令和 evidence 路径 |
| [`../../ANI-06-开发计划.md`](../../ANI-06-开发计划.md) | 全局开发计划；Section 零、Sprint 表与 Sprint14 章节记录本 gate 结果 |
| [`live-evidence/sprint14-resilience-live-evidence.json`](live-evidence/sprint14-resilience-live-evidence.json) | 脱敏 evidence；不得外推为 full platform production ready |

## 目标

为 Sprint14 三阶段韧性补一条真实环境 live gate：

- P0：真实 strong backend kill 后，data-plane readyz 进入 `fail` / HTTP 503，并在恢复后回到 `ok`。
- P1：真实 weak backend kill 后，readyz 进入 `degraded` 而不是整体失败，并在恢复后回到 `ok`。
- P2：删除当前 controller primary/leader pod 后，follower 通过 metadata-backed lease 接管。

## 实现

- 新增 `deploy/real-k8s-lab/sprint14-resilience-live-gate.yaml`：记录 `SPRINT14-CORE-RESILIENCE-LIVE-GATE` contract。
- 新增 `deploy/real-k8s-lab/sprint14-resilience-live-fixture.yaml`：在 `ani-sprint14-resilience` 隔离 namespace 内部署 Postgres、NATS、Redis、MinIO 与两副本 reconcile worker。
- 新增 `scripts/validate_sprint14_resilience_live_gate.py` 与测试：默认只校验 contract；`--live` 才会执行 `kubectl apply`、backend `pod delete`、短时 `scale --replicas=0`、controller primary pod delete、恢复轮询与脱敏 evidence 写入；故障断言失败时会恢复已缩容依赖。
- 新增 `make validate-sprint14-resilience-live-gate` contract gate。
- 修复真实 lab 暴露的 `/readyz` typed-nil dependency panic：`dependencyProbeChecks` 对 typed nil port 视为未配置，不调用其 `Health()`。
- Evidence 写入前会脱敏 URL、Kubernetes service DNS 和 IPv4 endpoint；验证后已清理隔离 namespace。

## 诚实边界

该 gate 证明 Sprint14 Core readyz/degradation/failover 语义可在真实 Kubernetes lab 的隔离 fixture 中执行并恢复。它不声称现有 Sprint13 单副本 Gateway、MinIO、Milvus、Redis、Postgres 或 NATS 已经具备自身 HA；也不替代 Redis/Postgres/MinIO/Milvus 生产 Operator 拓扑建设。

## 验证

```bash
make validate-sprint14-resilience-live-gate
python scripts/validate_sprint14_resilience_live_gate.py --live --evidence-output development-records/live-evidence/sprint14-resilience-live-evidence.json
```

2026-06-23 真实 lab 验证已通过：

- P0 baseline readyz `ok`；真实 Redis backend kill 后观察到 readyz fail/HTTP 503，恢复后回到 `ok`。
- P1 真实 MinIO/object-store backend kill 后 readyz 保持 HTTP 200 且状态 `degraded`，恢复后回到 `ok`。
- P2 删除当前 reconcile worker primary pod 后，metadata-backed lease 从 `worker-b` failover 到 `worker-a`，最终 readyz `ok`。
- Evidence 文件已扫描确认无 service DNS、URL、IPv4 endpoint、password、token、secret 或 kubeconfig 字符串。
