# SPRINT12-CLOSURE-A - Core Services 支撑 Handler 收口

> 批次类型：Closure
> 完成日期：2026-06-19
> 范围：仅 ANI Core，Tier1 local profile 收口

## 结论

Sprint 12 / Core「Services 支撑 Handler」已完成。A/B1/B2/B3 覆盖 `api/openapi/v1.yaml` 已声明但 Gateway 未实现的 19 个 Core handler 缺口 + 2 个 422 前置校验行为，均已通过 Core ports、runtime local adapters、Gateway handler、测试和文档闭环。

本收口不代表 real-provider、runtime ready 或 production ready。Sprint 13 的工作是沿用 Sprint 12 已建立的 port/adapter/router 边界接入真实 provider，并建立可复跑 live gate 与 evidence JSON。

## 已完成范围

- A `SPRINT12-KICKOFF-A`：完成真实代码与 `api/openapi/v1.yaml` diff，规划 19 个 handler + 2 个 422，拆分 B1/B2/B3。
- B1 `CORE-SVC-SUPPORT-OBSERVABILITY-A`：实例 logs/events/metrics/security-events/exec session、GPU inventory/occupancy、sandbox templates。
- B2 `CORE-SVC-SUPPORT-NETSTORE-A`：network routes、volume snapshots、filesystem mount-targets、K8s workloads，以及 searchVectorStore / createK8sCluster 前置不满足返回 422。
- B3 `CORE-SVC-SUPPORT-OBJVEC-A`：storage buckets、object upload/download 预签名 URL、vector document insert。

## Sprint 13 进入条件

Sprint 13 可以进入，但必须遵守以下边界：

- 不新增 Services 业务逻辑，不修改 `/api/v1/svc` 业务资源。
- 不绕过 `pkg/ports` 和 `pkg/adapters`；Gateway handler 不直接调用底层组件 SDK。
- 每个真实 provider 批次必须声明组件与版本、live gate 命令、evidence 输出路径和失败边界。
- 未跑通对应 live gate 前，Sprint 12 能力只能标记为 Tier1 local profile。

## 关联文档

- `repo/development-records/sprint12-kickoff-core-svc-support.md`
- `repo/development-records/core-svc-support-observability-a.md`
- `repo/development-records/core-svc-support-netstore-a.md`
- `repo/development-records/core-svc-support-objvec-a.md`
- `repo/development-records/sprint13-real-provider-readiness-plan.md`

## 验证入口

Sprint 12 收口门禁：

```bash
cd repo
make test
make validate-demo-instances validate-core-alpha validate-gpu-contracts
make validate-network-alpha validate-storage-alpha validate-vector-alpha
python scripts/validate_yaml.py api/openapi/v1.yaml
make validate-doc-entrypoints
git diff --check
```
