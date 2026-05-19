# SPEC-CORE-ALPHA-B — Core API Alpha Freeze Matrix

完成日期：2026-05-20
对应 Sprint：Sprint 2（2026-05-19 提前启动；计划窗口 2026-06-01 ~ 06-15）
验证结果：make test EXIT:0，make validate-core-alpha EXIT:0，make validate-demo-instances EXIT:0，make validate-instance-store EXIT:0，make validate-instance-service EXIT:0，make validate-architecture EXIT:0，git diff --check EXIT:0

## 实现了什么

完成 SPEC-CORE-ALPHA 的第二个可验证切片：新增机器可读的 Core API Alpha Freeze 矩阵，明确 Services P0 依赖的 instance path、operationId、RBAC scope、maturity、响应码、关键 request/response schema 字段、状态枚举和错误响应组件。`make validate-core-alpha` 现在会同时校验 API 契约、Gateway 路由、auth 边界、runtime port、迁移 token 和冻结矩阵，防止 Alpha Freeze 范围漂移。

## 关键文件改动

| 文件 | 新增/修改 | 说明 |
|---|---|---|
| `api/core-alpha-freeze.yaml` | 新增 | Core API Alpha 机器可读冻结矩阵 |
| `scripts/validate_core_alpha_contract.py` | 修改 | 校验冻结矩阵与 `api/openapi/v1.yaml`、Gateway 和 runtime port 一致 |
| `api/openapi/v1.yaml` | 修改 | 已在前置切片中补齐 Services P0 依赖的 instances path/schema/error/state/RBAC scope |
| `services/ani-gateway/internal/router/demo_instances.go` | 修改 | 已在前置切片中将主 `/instances` 路径接入 dev/local profile，并对齐嵌套 `gpu` 创建请求、必填 `idempotency_key` 和 lifecycle 409 冲突语义 |

## 完工标准达成

- [x] Services P0 instance 依赖路径有明确 Alpha 冻结矩阵
- [x] path、method、operationId、RBAC scope、maturity 和响应码被合同守卫校验
- [x] `CreateInstanceRequest`、`InstanceLifecycleRequest`、`InstanceRecord`、lifecycle action、operation timeline、state enum 和 error response 被合同守卫校验
- [x] Core instance 主路径不得回退为 `NOT_IMPLEMENTED` stub
- [x] Gateway create 请求支持 OpenAPI 冻结的 `gpu.vendor/model/count` 嵌套结构
- [x] Gateway `POST /instances` 与 lifecycle 入口显式拒绝空 `idempotency_key`
- [x] lifecycle precheck 冲突映射为 HTTP 409，与冻结矩阵错误语义一致
- [x] `make validate-core-alpha` 通过
- [x] `make test` 通过

## 备注

本切片完成 Sprint 2 的 Core API Alpha Freeze 收口。后续若修改冻结路径、字段类型、RBAC scope 或错误语义，必须按兼容性规则评估 breaking change。
