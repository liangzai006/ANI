# M1-INSTANCE-V-B — Container Rollback Local Profile

完成日期：2026-05-20
对应 Sprint：Sprint 2（2026-05-19 提前启动；计划窗口 2026-06-01 ~ 06-15）
验证结果：make test EXIT:0，make validate-core-alpha EXIT:0，make validate-demo-instances EXIT:0，make validate-instance-store EXIT:0，make validate-instance-service EXIT:0，make validate-architecture EXIT:0，git diff --check EXIT:0

## 实现了什么

完成 M1-INSTANCE-V 的第二个可验证切片：Container/GPU Container `rollback` lifecycle action 在 local/dev profile 中支持回滚到指定 `revision`，或在未指定时回滚到上一版 revision。回滚会更新 `container.revision`、将 `container.rollout_status` 标记为 `rolled_back`、追加 history 事件，并写入 operation timeline；本地 profile 不调用 provider executor。

## 关键文件改动

| 文件 | 新增/修改 | 说明 |
|---|---|---|
| `pkg/ports/workload_runtime.go` | 修改 | lifecycle request 增加 `Revision`，`WorkloadInstanceService` 增加 `Rollback` 方法 |
| `pkg/adapters/runtime/instance_service.go` | 修改 | rollback precheck、target revision 解析、本地状态更新和 `rollback_revision` timeline |
| `services/ani-gateway/internal/router/demo_instances.go` | 修改 | lifecycle handler 支持 `rollback` 和 `revision` 请求字段 |
| `scripts/validate_core_alpha_contract.py` | 修改 | 合同守卫覆盖 rollback service 方法和 Gateway handler |
| `pkg/adapters/runtime/instance_service_test.go` | 修改 | 覆盖 rollback 默认回上一版、不调用 provider、写 operation timeline |

## 完工标准达成

- [x] `rollback` lifecycle action 进入 Container/GPU Container local/dev profile
- [x] 未指定 revision 时回滚到上一版；指定 revision 时必须命中 history
- [x] rollback 更新 `container.revision/rollout_status/history`
- [x] rollback 写入 operation timeline，并与幂等语义保持一致
- [x] `make test` 通过
- [x] `make validate-architecture` 通过

## 备注

本切片完成 Core API Alpha 可依赖的 rollback 行为语义；provider-native rollout/rollback 执行留给 real provider beta 路径继续对齐。
