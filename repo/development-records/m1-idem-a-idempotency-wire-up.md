# M1-IDEM-A — 幂等性令牌集成

完成日期：2026-05-18
对应 Sprint：Sprint 1（2026-05-15 ~ 05-31）
验证结果：make build EXIT:0；make test EXIT:0；make validate-architecture passed；MetadataOperationStore atomic idempotency SQL unit test passed

## 实现了什么

将实例 create/lifecycle 的幂等语义从顺序回放推进到操作级幂等锁。Create 在进入 provider 编排前先写入 operation 作为幂等占位，重复请求直接返回已有 `operation_id`，不会再次进入 orchestrator；metadata store 使用 PostgreSQL `ON CONFLICT (tenant_id, idempotency_key)` 原子插入，支撑并发重试的唯一键冲突回放。

## 关键文件改动

| 文件 | 新增/修改 | 说明 |
|---|---|---|
| `pkg/ports/workload_runtime.go` | 修改 | CreateResult 增加 `IdempotentReplay`；OperationUpdate 支持回填 `instance_id` |
| `pkg/adapters/runtime/instance_service.go` | 修改 | Create 先占位 operation 再编排；重复 key 不重复执行；lifecycle 重复 key 不重复执行 |
| `pkg/adapters/runtime/operation_store.go` | 修改 | MetadataOperationStore 使用 `ON CONFLICT ... DO NOTHING` 原子写入并回放已有 operation |
| `pkg/bootstrap/deps.go` | 修改 | 正式 bootstrap wiring 接入 `MetadataOperationStore`，InstanceService 默认具备 DB 幂等边界 |
| `services/ani-gateway/internal/router/demo_instances.go` | 修改 | 幂等 replay 返回 409，并携带已有 `operation_id` |
| `pkg/adapters/runtime/instance_service_test.go` | 修改 | 覆盖重复 create 不重复进入 orchestrator、重复 resize 不新增 operation |
| `pkg/adapters/runtime/operation_store_test.go` | 新增 | 覆盖 MetadataOperationStore 生成原子幂等冲突 SQL |
| `pkg/bootstrap/deps_test.go` | 修改 | 覆盖 bootstrap 已接入 MetadataOperationStore |

## 完工标准达成

- [x] `make build` 全通
- [x] `make test` 全通
- [x] `make validate-architecture` 通过
- [x] 同 `idempotency_key` 重复 Create 返回同一 `operation_id`
- [x] 重复 Create 不创建第二个实例，不重复进入 orchestrator
- [x] MetadataOperationStore 具备 DB 唯一索引冲突原子回放 SQL
- [x] bootstrap 的正式 InstanceService 已接入 MetadataOperationStore

## 备注

当前单测覆盖幂等锁行为与 SQL 生成。真实 PostgreSQL 并发压测、HTTP 层完整 409 payload 回归，以及已部署环境的迁移兼容验证，应在后续 integration profile 中补齐。
