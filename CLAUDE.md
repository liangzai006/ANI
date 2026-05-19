# CLAUDE.md

This file provides mandatory guidance for Claude Code / Codex / Cursor / GPT coding agents working in this repository.

> 本文件是 AI/人类开发的工程约定入口。详细产品规划、路线图和历史归档不在本文重复维护，统一从 `ANI-DOCS-INDEX.md` 跳转。

---

## 0. 当前状态

```text
当前阶段：Phase 1 / Sprint 3
当前优先级：M1-NETWORK-A → M1-STORAGE-A → SDK-ALPHA-A
当前不是 Phase 2：Phase 2 是 2026-10 以后延期能力
下一步入口：repo/CURRENT-SPRINT.md
文档导航：ANI-DOCS-INDEX.md
产品定义版本：V8.3
首个正式版本目标：v1.0.0，2026-09-30
```

---

## 1. 5 分钟快速上手

### Step 1：先读入口

按顺序读：

```text
1. ANI-DOCS-INDEX.md
2. repo/CURRENT-SPRINT.md
3. ANI-06-开发计划.md 的 Section 零和当前 Sprint
4. repo/api/openapi/v1.yaml
5. repo/pkg/ports/workload_runtime.go
```

### Step 2：验证环境

```bash
cd repo
make build
make test
make validate-architecture
```

如果失败，先看 `repo/CURRENT-SPRINT.md` 的「环境启动」和当前批次验收说明。

### Step 3：知道当前要做什么

当前执行只看 `repo/CURRENT-SPRINT.md`。不要从历史批次、旧 handoff 文档或 Phase 2 规划倒推出当前任务。

---

## 2. 文档真实来源

| 问题 | 真实来源 |
|---|---|
| 文档导航和阅读顺序 | `ANI-DOCS-INDEX.md` |
| 当前 Sprint 任务、状态、验收命令 | `repo/CURRENT-SPRINT.md` |
| 全局进度、Services 解锁门禁、延期项 | `ANI-06-开发计划.md` |
| 产品功能边界 | `ANI-02-产品功能设计.md` |
| 路线图阶段与版本关系 | `ANI-03-产品路线图.md` |
| 版本、tag、发布兼容性 | `ANI-12-版本管理策略.md` |
| 代码实现规范 | `ANI-11-代码实现规范.md` |
| 开源组件 ports/adapters 边界 | `ANI-13-开源组件松耦合适配器架构.md` |
| 已完成批次归档 | `repo/development-records/README.md` |
| Core API 契约 | `repo/api/openapi/v1.yaml` |
| Services API 契约 | `repo/api/openapi/services/v1.yaml` |

若进度状态冲突，以 `ANI-06-开发计划.md` Section 零和 `repo/CURRENT-SPRINT.md` 为准。若工程约定冲突，以本文的强制规则为准。

---

## 3. 分层架构强制约束

ANI 分为两层：

| 层 | 职责 | 强制边界 |
|---|---|---|
| ANI Core | 基础设施平台层：计算、存储、网络、身份、安全、计量、可观测、平台支撑 | 本小组负责；只输出 REST API、SDK、CLI；不得包含模型推理/RAG/PaaS 业务逻辑 |
| ANI Services | 云服务层：IaaS 控制台、AI 全生命周期、AI-Native 应用、PaaS 托管服务 | 另一小组负责；只能通过 Core REST API / SDK 调用 Core；禁止 import Core 代码包或直接操作底层组件 |

当前仓库中 `repo/services/model-service/` 和 `repo/services/kb-service/` 逻辑属于 ANI Services，暂存于 monorepo。Core 服务禁止调用它们；它们也不得 import Core 代码包，只能调用 Core API。

---

## 4. API 契约强制规则

1. `repo/api/openapi/v1.yaml` 是 ANI Core 对外 REST API 的唯一真实来源。
2. 团队内统一称为 **API 契约**，避免说“OpenAPI 接口”或“OpenAI 接口”。
3. 所有新 Core API 必须先改 API 契约，再写实现、测试和 SDK。
4. Core API `servers[0].url` 必须为 `https://{host}/api/v1`。
5. Services API `servers[0].url` 必须为 `https://{host}/api/v1/svc`。
6. `repo/api/openapi/v1.yaml` 只能包含基础设施资源，例如 instances、networks、volumes、auth、gpu-inventory。
7. models、inference-services、knowledge-bases 等业务资源必须维护在 `repo/api/openapi/services/v1.yaml`。
8. Proto 是内部 gRPC 实现细节；当 Proto 与 REST schema 描述同一资源发生冲突时，以 API 契约为准。

### 当前冻结节奏

| 日期 | 门禁 |
|---|---|
| 2026-06-10 | Core API Alpha Freeze |
| 2026-06-20 | SDK Alpha |
| 2026-06-30 | Core Dev Profile Ready |
| 2026-08-15 | Core API Beta Freeze |

Services P0 依赖路径在对应门禁后不允许无 owner/date 的 stub、mock success 或 `NOT_IMPLEMENTED`。

---

## 5. SDK 生成规则

| SDK | 来源 |
|---|---|
| Go / Python / TypeScript / Java Core SDK | `repo/api/openapi/v1.yaml` |
| Python / TypeScript / Java Services SDK | `repo/api/openapi/services/v1.yaml` |

SDK 不得包含对方层资源类型。Services 团队使用 Core SDK，不 import Core 代码包。

---

## 6. API 工程约定

### 向后兼容

Core API v1 生命周期内：

- 允许新增可选 request 字段、response 字段、端点和枚举值。
- 删除字段、改字段类型、删除端点、修改 HTTP 方法、修改错误语义均属于破坏性变更。
- 破坏性变更必须新建 v2，或按 `ANI-12-版本管理策略.md` 判断版本影响。

### 幂等性

所有 POST 创建和有副作用的 PUT/PATCH 必须支持 `idempotency_key`：

- 同一 `(tenant_id, idempotency_key)` 在 24 小时内返回同一结果。
- 客户端重试必须复用同一个 idempotency_key。
- SDK 应提供 idempotency_key 辅助能力。

### 控制面与数据面分离

- ani-gateway/auth-service 故障时，已运行 VM/容器/Sandbox 必须继续运行。
- 状态对齐必须通过独立 reconcile controller 或等价后台机制完成，不能只依赖 API 请求触发。
- 生命周期操作必须写入 operation timeline、审计、失败原因和重试资格。

### Workload Identity

运行中的实例调用 ANI Core API 禁止使用长期静态 API Key。P0 使用生命周期绑定 scoped API Key；P1 再升级为短期 token / IRSA 风格。

---

## 7. 组件边界强制规则

1. 业务服务不得直接依赖 MinIO、Milvus、NATS JetStream、Redis、Harbor、CloudNativePG 等组件 SDK。
2. 除 Kubernetes API 的 bounded runtime 模块外，组件访问必须经过 `pkg/ports/` 和 `pkg/adapters/`。
3. VM、Container、GPU Container、Sandbox、Batch Job、Notebook、K8s Cluster、BM、DPU 都必须先经过 `WorkloadRuntime` 能力抽象。
4. 异构 GPU 发现、分类和调度必须经过 `GPUInventory` 能力抽象。
5. `make test` 会执行或应覆盖架构边界检查；新增直接组件 SDK 导入必须有显式 allowlist 和迁移批次理由。

---

## 8. 开发阶段命名规则

1. `ANI-06` 中的模块编号是产品开发计划编号。
2. 代码生成批次使用可回溯命名，例如 `M2.1-TASK-A`、`M1-INSTANCE-U`。
3. 禁止继续使用 `Stage 3A/3B/3C` 这类容易误解为模块编号的名称；历史出现时必须注明旧名。
4. 当前整体进度在 `ANI-06-开发计划.md` Section 零。
5. 当前 Sprint 任务在 `repo/CURRENT-SPRINT.md`。
6. 已完成批次归档在 `repo/development-records/README.md`。

---

## 9. 完工闭环规约

### 批次完成时

触发条件：`make test`、当前批次验收命令和必要架构检查通过。

必须更新：

```text
1. repo/development-records/{批次名}.md
2. repo/development-records/README.md
3. repo/CURRENT-SPRINT.md
4. ANI-06-开发计划.md Section 零
```

批次记录文件使用 `repo/development-records/TEMPLATE.md`。

### Sprint 完成时

必须更新：

```text
1. ANI-06-开发计划.md Section 零：当前 Sprint → 已完成，下一 Sprint → 当前
2. repo/CURRENT-SPRINT.md：整体切换到下一 Sprint
3. ANI-DOCS-INDEX.md：当前状态和门禁如有变化则同步
```

---

## 10. 提交前验证

至少执行：

```bash
cd repo
make test
make validate-architecture
git diff --check
```

发布或预发布还必须遵守 `ANI-12-版本管理策略.md` 的发布门禁。

---

## 11. 版本管理

1. ANI 使用 SemVer：`vMAJOR.MINOR.PATCH[-pre.N]`。
2. 首个正式版本是 `v1.0.0`，目标日期 `2026-09-30`。
3. 当前仍处于 `v0.x` 开发期，不得标记为 `v1.0.0` 或 RC。
4. 产品阶段、开发模块、代码生成批次与版本号独立。
5. API、Proto、DB、CRD、Helm、认证/安全模型的破坏性变更必须按 `ANI-12` 判断版本影响。

---

## 12. Karpathy 四条开发原则

### 原则一：先思考，再编码
**不要假设。不要掩饰困惑。要揭示取舍。**

- 如果需求有歧义，明确说出来并询问，而不是悄悄选一种猜测实现
- 存在多种合理方案时，列出并说明各方案的取舍，由人决策
- 面对复杂问题，先陈述理解再动手
- 遇到不确定的地方，停下来问，而不是带着疑惑继续

### 原则二：用能解决问题的最小代码
**拒绝一切带有猜想的实现。**

- 不实现没被要求的功能，哪怕"感觉以后用得到"
- 不为一次性代码创建抽象层
- 不加"灵活性""可配置性"等未被要求的扩展点
- 200 行能写成 50 行的，重写

### 原则三：只触碰你必须改动的部分
**只清理你自己制造的脏。**

- 不顺手"优化"任务范围之外的代码、注释或格式
- 不重构没坏的东西
- 保持现有代码风格，即使你有不同偏好
- 发现死代码，提出来，不要自作主张删除

### 原则四：定义成功标准，循环迭代直到验证通过
**把任务转化为可验证的目标。**

- 每个任务开始前明确"什么状态算完成"
- 多步骤任务先列出简短计划和验证步骤
- 优先给 Claude 成功标准而非操作指令：不是"修复这个 bug"，而是"写一个能复现 bug 的测试，再修复它"
