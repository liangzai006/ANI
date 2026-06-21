# SDK-SERVICES-IDEMPOTENCY-SEPARATION-A - Services SDK idempotency boundary fix

完成日期：2026-06-21
对应范围：Sprint 4 SDK 回归门禁 / Sprint 12 Core SDK 契约漂移后续修复

## 背景

Sprint 12 Core SDK 重生成后，`validate-sdk-alpha` 暴露 Services SDK 相对 `api/openapi/services/v1.yaml` 已过期；重生成 Services SDK 后，`validate-sdk-beta` 又把 Services 自己的幂等 operationId 误判为 Core 幂等操作泄漏。

根因不是 Services 业务代码需要继续开发，而是 SDK beta 校验器把“Services SDK 不得声明 Core idempotency operations”实现成了“Services SDK 不得声明任何 idempotency operations”。这与 Services 契约中已有的 `idempotency_key` 写操作不一致。

## 实现了什么

- `scripts/validate_sdk_beta.py` 改为只拒绝 Core SDK 与 Services SDK 的 `idempotencyOperations` 交集。
- 新增 `scripts/validate_sdk_beta_test.py`，覆盖 Services 自有幂等操作允许、Core 幂等操作交叉泄漏拒绝两种情况。
- `make validate-sdk-beta` 先运行该回归测试，再运行 SDK beta 校验和 SDK alpha 校验。
- `CURRENT-SPRINT.md` 的 Sprint 13 基线回归入口补回 SDK beta / SDK mock smoke / Sprint 4 closure。
- 重新执行 `make gen-core-sdk` 后，Core/Services 四语言 SDK metadata 与各自 OpenAPI 契约对齐。

## 边界

- 本批不修改 `api/openapi/v1.yaml` 或 `api/openapi/services/v1.yaml`。
- 本批不新增、修改或补全 Services 业务逻辑；仅更新由既有 Services OpenAPI 契约生成的 SDK artifact。
- Services SDK 可以包含 Services 自己的 `idempotencyOperations`，但不得包含 Core 的 operationId。

## 完工标准

- [x] `make gen-core-sdk`
- [x] `python scripts/validate_sdk_beta_test.py`
- [x] `make validate-sdk-alpha`
- [x] `make validate-sdk-beta`
- [x] `make validate-sprint4-closure`
- [x] `make test`
- [x] `make validate-architecture`
- [x] `make validate-doc-entrypoints`
- [x] `git diff --check`
