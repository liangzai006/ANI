# KuberCloud ANI · 文档导航与一致性矩阵

> 最后更新：2026-05-19
> 目的：让人类开发者和 AI 工具在 5 分钟内判断当前开发阶段、文档职责、下一步入口和闭环规则。

---

## 当前结论

```text
当前阶段：Phase 1 / Sprint 2
当前不是 Phase 2：Phase 2 指 2026-10 以后延期能力
当前优先级：SPEC-CORE-ALPHA → M1-INSTANCE-U → M1-INSTANCE-V
刚完成：Sprint 1 Foundation + M2.2 Auth Final（2026-05-18）
下一步入口：repo/CURRENT-SPRINT.md
```

Sprint 2 的核心任务是提前稳定 ANI Core 对 ANI Services 的 P0 依赖：Core API Alpha、VM 生产级操作、Container/GPU 深度能力。

---

## 唯一真实来源矩阵

| 问题 | 先看哪里 | 说明 |
|---|---|---|
| 当前做什么 | `repo/CURRENT-SPRINT.md` | 当前 Sprint 的执行入口，状态、任务、验收命令以它为准 |
| 全局开发节奏 | `ANI-06-开发计划.md` | Sprint 计划、Services 解锁门禁、延期项以它为准 |
| 产品功能边界 | `ANI-02-产品功能设计.md` | Core/Services 分层、v1.0.0 P0 能力边界以它为准 |
| 路线图阶段 | `ANI-03-产品路线图.md` | Phase 1/2/3 与版本号关系以它为准 |
| 工程约定和 AI 工作规则 | `CLAUDE.md` | AI/人类开发前必须先读；架构、提交、闭环规则以它为准 |
| API 契约 | `repo/api/openapi/v1.yaml` | Core REST API 唯一真实来源 |
| Services API 契约 | `repo/api/openapi/services/v1.yaml` | Services 层业务 API 契约 |
| 已完成批次 | `repo/development-records/README.md` | 历史完成记录索引，不作为当前任务清单 |
| 单批次细节 | `repo/development-records/*.md` | 追溯实现、验证和关键文件时再读 |
| 审查提示词模板 | `ANI-10-GPT审查提示词集.md` | 只作为审查问题模板；内置示例不得作为当前事实来源 |

---

## 推荐阅读路径

### 人类开发者

1. `ANI-DOCS-INDEX.md`
2. `CLAUDE.md` 的 5 分钟快速上手
3. `repo/CURRENT-SPRINT.md`
4. `ANI-06-开发计划.md` Section 零和 Sprint 2
5. `repo/api/openapi/v1.yaml` + 相关代码入口

### AI 编码工具

1. 必须先读 `CLAUDE.md`
2. 再读 `repo/CURRENT-SPRINT.md`
3. 开发前检查 `ANI-06-开发计划.md` Section 零
4. 涉及接口时先改 `repo/api/openapi/v1.yaml`
5. 完成后按 `CLAUDE.md` 的进度更新规约闭环

---

## 当前开发门禁

| 日期 | 门禁 | 当前影响 |
|---|---|---|
| 2026-05-31 | P0 依赖矩阵冻结 | Sprint 2 必须输出 Services P0 依赖清单和 maturity |
| 2026-06-10 | Core API Alpha Freeze | 当前优先做 SPEC-CORE-ALPHA |
| 2026-06-20 | SDK Alpha | Go/Python/TypeScript/Java SDK 必须可生成、可 import |
| 2026-06-30 | Core Dev Profile Ready | Services 团队可基于 SDK + dev/local profile 做端到端开发 |
| 2026-09-30 | v1.0.0 Final Delivery | ANI Core v1.0.0 + ANI Services P0 |

---

## 文档维护规则

1. 当前阶段变更时，必须同步 `ANI-DOCS-INDEX.md`、`ANI-06-开发计划.md` 和 `repo/CURRENT-SPRINT.md`。
2. 批次完成时，必须新增或更新 `repo/development-records/{批次名}.md`，并更新 `repo/development-records/README.md`。
3. 历史归档文档允许保留当时日期和上下文，不反向改写为当前态。
4. 若 `CLAUDE.md` 与其它文档冲突，以 `CLAUDE.md` 的工程规则为准；若是进度状态冲突，以 `ANI-06-开发计划.md` Section 零和 `repo/CURRENT-SPRINT.md` 为准。
5. 不把大段完成细节堆到入口文档；入口文档只保留当前状态、下一步和链接。
6. 更换 AI 模型或工具时，必须先重新读取本文件、`CLAUDE.md` 和 `repo/CURRENT-SPRINT.md`，不得依赖上一个会话的记忆。
