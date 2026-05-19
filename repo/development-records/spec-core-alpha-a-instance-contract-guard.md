# SPEC-CORE-ALPHA-A — Instances Alpha Contract Guard

完成日期：2026-05-19
对应 Sprint：Sprint 2（2026-05-19 提前启动；计划窗口 2026-06-01 ~ 06-15）
验证结果：make test EXIT:0，make validate-core-alpha EXIT:0，make validate-demo-instances EXIT:0，make validate-architecture EXIT:0，git diff --check EXIT:0

## 实现了什么

完成 Sprint 2 的第一个 Core API Alpha 可验证切片：将 Services P0 依赖的 `/api/v1/instances` 主路径、实例操作查询、VM console session、生命周期操作纳入 Core API 契约，并用合同守卫固定 path、schema、error、state 和 RBAC scope。Gateway 主路径暂复用本地 instance service/dev profile，避免 Services 团队继续依赖 `/api/v1/demo/instances`。

## P0 依赖矩阵

| 依赖 | Current maturity | Target maturity | 本切片结果 |
|---|---|---|---|
| instances path | demo/local profile | Core Alpha path frozen | `/instances`、`/instances/{id}`、`/instances/{id}/lifecycle`、`/instances/{id}/console` 已入契约和 Gateway 路由 |
| operations | local operation store | Alpha query contract | `/instances/{id}/operations`、`/instance-operations/{id}` 补齐 RBAC scope 和 403 |
| idempotency | create/lifecycle service wire-up | Alpha required field | create/lifecycle request schema 均要求 `idempotency_key` |
| RBAC scope | auth-service 可用，instances scope 未冻结 | Alpha scope frozen | `scope:instances:read/create/update/console` 写入契约并由守卫校验 |
| NOT_IMPLEMENTED | Services 遗留路径仍有 stubs | P0 Core path 不可 stub | 守卫禁止 Core Alpha instance 路径出现在 `router/stubs.go` |

## 关键文件改动

| 文件 | 新增/修改 | 说明 |
|---|---|---|
| `api/openapi/v1.yaml` | 修改 | 新增 Core `/instances` Alpha path、VM/Container/GPU 状态字段、生命周期/console schema 和 RBAC scope |
| `services/ani-gateway/internal/router/demo_instances.go` | 修改 | 将本地 instance service 暴露到 `/api/v1/instances` 主路径，并对生命周期响应返回 `operation_id` |
| `scripts/validate_core_alpha_contract.py` | 新增 | 校验 Core Alpha path/schema/RBAC scope/Gateway route/Auth protected boundary |
| `Makefile` | 修改 | 新增 `make validate-core-alpha`，并扩大 `validate-demo-instances` 的测试匹配范围 |
| `repo/CURRENT-SPRINT.md` | 修改 | 记录 SPEC-CORE-ALPHA-A 已完成，并为后续 SPEC-CORE-ALPHA-B 冻结矩阵收口保留入口 |
| `ANI-06-开发计划.md` | 修改 | 同步 Sprint 2 状态快照中的当前优先项进展 |

## 完工标准达成

- [x] `/api/v1/instances` 主路径不再只停留在 demo 路径，Gateway 已注册可开发依赖的 dev/local profile 路由
- [x] create/lifecycle/console/operation path、schema、error、state、RBAC scope 进入 Core API Alpha 契约
- [x] `make validate-core-alpha` 通过
- [x] `make validate-demo-instances` 通过
- [x] `make test` 通过
- [x] `make validate-architecture` 通过
- [x] `git diff --check` 通过

## 备注

本切片完成后，SPEC-CORE-ALPHA 主批次已继续由 `SPEC-CORE-ALPHA-B` 收口为机器可读冻结矩阵；M1-INSTANCE-U/V 的 VM、Container 和 GPU 本地 profile 深度也已在后续切片完成并归档。
