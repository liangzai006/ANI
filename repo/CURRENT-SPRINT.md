# ANI · 当前冲刺上手指南

> **新开发者（人类或 AI 工具）的第一个入口文件。**
> 读完本文件，5 分钟内明确：当前做什么、怎么开始、怎么验证完成。
> 已完成批次只查 `repo/development-records/README.md`，不要把历史细节塞回本文。

---

## 当前冲刺

| 字段 | 值 |
|---|---|
| **冲刺编号** | Sprint 2 |
| **时间范围** | 2026-05-19 提前启动；计划窗口 2026-06-01 → 2026-06-15 |
| **主题** | VM & Container/GPU 生产深度 + Core API Alpha Freeze |
| **核心批次** | SPEC-CORE-ALPHA + M1-INSTANCE-U + M1-INSTANCE-V |
| **前置验证** | Sprint 1 全部完成；M2.2 Auth Final 已通过合同守卫和 Docker Dex smoke |

---

## 本冲刺目标

Sprint 2 的目标不是进入 Phase 2，而是在 Phase 1 内把 ANI Core 对 ANI Services 的 P0 依赖提前稳定下来。

1. 冻结 Services P0 依赖的 Core API Alpha：path、schema、error、state、RBAC scope。
2. 将 `/api/v1/instances` 从 demo/stub/local-only 推进到 VM、container、gpu_container 可开发依赖的 Core API。
3. 补齐 VM 生产级操作：终止保护、console/VNC session、快照、磁盘绑定、SSH 连接信息。
4. 补齐 Container/GPU 深度：副本、滚动更新、回滚、历史、GPU 调度原因和利用率。
5. 每个可验证切片必须有测试、验证命令和 `development-records` 闭环记录。

---

## P0：SPEC-CORE-ALPHA

**状态：🔄 当前优先**

**为什么先做：** Services 团队需要稳定 API 和 SDK 节奏。如果 API 契约继续滞后，Services 会被迫猜接口或反复返工。

### 技术入口

```
api/openapi/v1.yaml                         ← Core API 契约唯一真实来源
services/ani-gateway/internal/router/       ← Gateway REST 路由与 handler
services/ani-gateway/internal/router/stubs.go
services/ani-gateway/internal/router/demo_instances.go
pkg/ports/workload_runtime.go               ← WorkloadRuntime 能力边界
pkg/adapters/runtime/                       ← 当前 instance 编排实现
development-records/m2-2-auth-final-production-closeout.md
```

### 交付物

- P0 依赖矩阵：instances、auth、operations、idempotency、RBAC scope 的 current/target maturity。
- API Alpha 冻结清单：Services P0 依赖的 path/schema/error/state/RBAC scope。
- `NOT_IMPLEMENTED` 盘点：Services P0 依赖路径不得无 owner/date 地保留 stub。
- 合同守卫：新增或更新契约校验，防止 Gateway route、API 契约和鉴权边界漂移。

### 验收命令

```bash
make test
make validate-architecture
git diff --check
```

---

## P0：M1-INSTANCE-U

**状态：⏳ 待开始**

**主题：VM 生产级操作**

### 最小实现切片

1. 在 API 契约中明确 VM action、状态机、错误码和 RBAC scope。
2. 支持 `termination_protection`，对 delete/stop/rebuild 等危险操作给出明确 precheck。
3. 提供 console/VNC session 申请接口，返回带过期时间的 session 信息。
4. 补齐快照、磁盘绑定、SSH 连接信息的 schema 与本地 profile 行为。
5. 关键操作写入 operation timeline，并与幂等性语义保持一致。

### 验收方向

```bash
make test
# 定向测试应覆盖：
# - 开启 termination_protection 后危险操作被拒绝
# - console/VNC session 返回 session_id/url/expires_at
# - VM 操作返回 operation_id，并可查询 timeline
```

---

## P0：M1-INSTANCE-V

**状态：⏳ 待开始**

**主题：Container/GPU 容器生产深度**

### 最小实现切片

1. Container 实例支持 replicas、revision、rollout 状态和 history。
2. 支持 rollback 到上一版本，并写入 operation timeline。
3. GPU 容器状态包含 `gpu_scheduling_reason` 和 `gpu_utilization`。
4. API 契约明确 container/gpu_container 的字段边界，避免 Services 自行猜测。

### 验收方向

```bash
make test
# 定向测试应覆盖：
# - container rollout 产生新 revision
# - rollback 恢复上一 revision
# - gpu_container 返回调度原因和利用率字段
```

---

## 本冲刺不做

- 不实现 Phase 2 延期项。
- 不把 Services 业务逻辑写进 Core。
- 不绕过 `pkg/ports/` 直接调用 K8s/KubeVirt/MinIO/Milvus SDK。
- 不为赶进度保留没有 owner/date 的 Services P0 stub。
- 不在没有 API 契约和测试的情况下直接生成实现代码。

---

## 代码结构 10 分钟导航

```
必读（按顺序）：
  1. CLAUDE.md
  2. ANI-DOCS-INDEX.md
  3. ANI-06-开发计划.md 的 Section 零和 Sprint 2
  4. api/openapi/v1.yaml
  5. pkg/ports/workload_runtime.go
  6. pkg/adapters/runtime/instance_orchestrator.go

查历史：
  - repo/development-records/README.md
  - repo/development-records/m2-2-auth-final-production-closeout.md
  - repo/development-records/2026-05-12-instance-lifecycle-implementation-plan.md
```

---

## 环境启动

```bash
cd /path/to/ANI/repo

make build
make test
make validate-architecture
```

Docker 只用于需要真实外部依赖的 smoke 测试，例如 Dex OIDC。常规 Sprint 2 开发应优先通过单元测试、合同测试和本地 profile 验证推进，不要因为没有完整 K8s 环境而停滞。

---

## 完工后必做

每完成一个批次或可独立验收切片，按顺序执行：

```text
1. make test
2. make validate-architecture
3. git diff --check
4. 新建或更新 repo/development-records/{批次名}.md
5. 更新 repo/development-records/README.md
6. 更新本文件对应批次状态
7. 更新 ANI-06-开发计划.md Section 零对应批次状态
```

Sprint 2 全部完成后：

```text
1. ANI-06 Section 零：Sprint 2 标记为已完成，Sprint 3 标记为当前
2. 本文件整体重写为 Sprint 3 内容
3. 记录 Core API Alpha Freeze 的冻结范围和后续 breaking change 审批规则
```

完整规约说明：`CLAUDE.md` → "📋 开发进度更新规约"。

---

*Sprint 2 负责人：[填入]　最后更新：2026-05-19*
