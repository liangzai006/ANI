# Phase 4 执行手册 — AI Coding 入口

**适用对象**: 人工 + 任何 AI coding agent（Claude / GPT / Gemini / Cursor 等均适用）  
**当前状态**: Phase 0-3 已完成，可直接执行 Phase 4  
**入口文件**: 本文件是 Phase 4 的唯一启动入口

---

## 快速定位（30 秒读懂当前状态）

| 文件 | 说明 |
|------|------|
| `repo/api/openapi/services/v1.yaml` | Services API 契约（31 paths，已含 GPU容器/Sandbox/租户管理），**这是 handler 的唯一数据来源** |
| `repo/development-records/SERVICES-TEAM-TASKS.md` | 21 个 Services handler 任务块（TASK-SVC-001 ~ TASK-SVC-021） |
| `repo/development-records/CORE-TEAM-TASKS.md` | 3 个 Core handler 任务块（TASK-CORE-001 ~ TASK-CORE-003） |
| `repo/development-records/TASK-DEPENDENCY-MAP.md` | 任务依赖图，**告诉你哪些任务可以立即并行启动** |
| `repo/services/ani-gateway/internal/router/stubs.go` | 当前所有 501 占位 handler，Phase 4 的目标是消灭它们 |

---

## 第一步：确认从哪个批次开始

打开 `TASK-DEPENDENCY-MAP.md`，找到"**第一批：无前置依赖**"部分：

```
TASK-SVC-001  listModels
TASK-SVC-007  listInferenceServices
TASK-SVC-011  listKnowledgeBases
TASK-SVC-017  listGpuContainers
TASK-SVC-019  listSandboxes
TASK-SVC-021  listTenantMembers
TASK-CORE-001 Branding handlers
TASK-CORE-002 Task handlers
```

这 8 个任务**可以同时分配给多个 AI coding session 并行执行**，互不干扰。

---

## 第二步：给 AI coding agent 的标准提示

### 2.1 单任务执行提示（通用模板，替换 {TASK_ID} 即可）

```
你是一名 Go 后端开发者，正在为 ANI 平台的 ani-gateway 服务实现 HTTP handler。

请按顺序读取以下文件：
1. repo/development-records/SERVICES-TEAM-TASKS.md（找到 {TASK_ID} 任务块）
2. repo/api/openapi/services/v1.yaml（找到对应 operationId 的完整 schema 定义）
3. repo/services/ani-gateway/internal/router/stubs.go（了解当前 notImplemented 结构）
4. repo/services/ani-gateway/internal/router/network_resources.go（参考现有 handler 文件风格）
5. repo/services/ani-gateway/internal/middleware/auth.go（了解 tenant_id 提取方式）

然后执行：
- 按任务块"Files"列出的路径新建或修改 Go 文件
- 实现"Handler 逻辑"中描述的步骤（先返回空列表，不对接真实下游服务）
- 必须从 c.MustGet("tenant_id").(string) 提取租户 ID
- 错误返回格式：{"code":"...", "message":"...", "request_id":"..."}
- 完成后运行任务块中的"验收命令"，确认返回 200

最后运行：make test && make validate-architecture，确认不报错。
```

### 2.2 多任务并行分配（同时开多个独立 session）

```
Session A → TASK-SVC-001（新建 model_resources.go 骨架）
Session B → TASK-SVC-007（新建 inference_resources.go 骨架）
Session C → TASK-SVC-011（新建 kb_resources.go 骨架）
Session D → TASK-CORE-001（新建 branding_resources.go）
```

每个 session 操作不同文件，不会产生冲突，可并行。

---

## 第三步：Handler 代码的固定结构

每个新 `.go` handler 文件**必须遵循以下结构**（来自现有 `network_resources.go` 的模式）：

```go
package router

import (
    "context"
    "net/http"
    "os"

    "github.com/cloudwego/hertz/pkg/app"
)

// registerModels 由 router.go 的 RegisterWithOptions 调用，注册到 svc 路由组
func registerModels(svc *app.RouterGroup) {
    svc.GET("/models", listModels)
    svc.POST("/models", createModel)
    svc.GET("/models/:model_id", getModel)
    svc.DELETE("/models/:model_id", deleteModel)
}

func listModels(ctx context.Context, c *app.RequestContext) {
    tenantID := c.MustGet("tenant_id").(string)
    _ = tenantID // 第一批：先返回空列表，下游对接是第二批工作

    // TODO 第二批: addr := os.Getenv("MODEL_SERVICE_ADDR")
    _ = os.Getenv

    c.JSON(http.StatusOK, map[string]interface{}{
        "items":       []interface{}{},
        "next_cursor": nil,
    })
}
```

**禁止 import**：`pkg/adapters`、`pkg/ports`（违反架构边界会导致 `make validate-architecture` 失败）。  
**允许 import**：`pkg/generated/pb/`（proto 数据结构）。

---

## 第四步：修改 stubs.go 的方式

完成一个 TASK 后，从 `stubs.go` 删除对应的 register 函数（新文件里已有新实现），**保留 router.go 里的调用不变**。

**修改前（stubs.go）：**
```go
func registerModels(svc *app.RouterGroup) {
    svc.GET("/models", notImplemented)
    svc.POST("/models", notImplemented)
    // ...
}
```

**修改后**：删除 `stubs.go` 里的 `registerModels` 函数，改为在 `model_resources.go` 里定义同名函数。`router.go` 里的 `registerModels(svc)` 调用**不需要改**，Go 编译器会自动找到新文件里的函数。

---

## 第五步：验收

```bash
# 编译检查
cd repo && go build ./services/ani-gateway/...

# 单元测试
make test

# 架构边界检查
make validate-architecture

# 本地启动 ani-gateway（ANI_AUTH_MODE=dev 跳过 auth 检查）
ANI_AUTH_MODE=dev go run ./services/ani-gateway/...

# 在另一个终端验证（每个 TASK 对应一行）
curl -H "X-Dev-Tenant-ID: test" http://localhost:8080/api/v1/svc/models
curl -H "X-Dev-Tenant-ID: test" http://localhost:8080/api/v1/svc/inference-services
curl -H "X-Dev-Tenant-ID: test" http://localhost:8080/api/v1/svc/knowledge-bases
curl -H "X-Dev-Tenant-ID: test" http://localhost:8080/api/v1/svc/gpu-containers
curl -H "X-Dev-Tenant-ID: test" http://localhost:8080/api/v1/svc/sandboxes
curl -H "X-Dev-Tenant-ID: test" http://localhost:8080/api/v1/svc/tenant/members
curl http://localhost:8080/api/v1/branding
```

期望：所有接口返回 200（不再返回 501）。

---

## 第六步：完成后的文档闭环（CLAUDE.md 强制要求）

每完成一个 Feature batch，必须同步更新 4 个文件：

```
1. repo/development-records/{批次名}.md  → 新建（如 M2.2-TASK-SVC-001.md）
2. repo/development-records/README.md    → 追加一行索引
3. repo/CURRENT-SPRINT.md               → 更新 Sprint 状态
4. ANI-06-开发计划.md                   → Section 零更新进度
```

验证命令：`make validate-doc-entrypoints`

---

## 附 A：新会话/换 LLM 时的上下文加载指令

**把以下内容原文复制给新的 AI coding agent：**

```
请读取以下文件，了解 ANI 项目当前开发状态后再开始工作：

【必读 - 强制规则和当前状态】
1. repo/CLAUDE.md                                       ← 架构边界强制规则
2. repo/CURRENT-SPRINT.md                               ← 当前 Sprint 状态

【必读 - 执行入口】
3. repo/development-records/TASK-DEPENDENCY-MAP.md      ← 任务批次和依赖关系
4. repo/development-records/PHASE4-EXECUTION-GUIDE.md   ← 本执行手册

【按需读取 - 执行某个 TASK 时】
5. repo/development-records/SERVICES-TEAM-TASKS.md      ← Services 任务详情
6. repo/development-records/CORE-TEAM-TASKS.md          ← Core 任务详情
7. repo/api/openapi/services/v1.yaml                    ← API 契约（handler 的数据来源）
8. repo/services/ani-gateway/internal/router/stubs.go   ← 当前 501 占位符

【当前目标】
执行第一批无前置依赖的 TASK（见 TASK-DEPENDENCY-MAP.md 第一批列表）。
为 stubs.go 中每个 notImplemented 创建真实 handler 骨架。
第一批只需返回 200 空列表，不对接真实下游服务。
```

---

## 附 B：TASK 执行路线图

```
【第一批 - 立即可并行执行】
TASK-SVC-001  model_resources.go 骨架       → /svc/models → 200
TASK-SVC-007  inference_resources.go 骨架   → /svc/inference-services → 200
TASK-SVC-011  kb_resources.go 骨架          → /svc/knowledge-bases → 200
TASK-SVC-017  gpu_container_resources.go    → /svc/gpu-containers → 200
TASK-SVC-019  sandbox_resources.go          → /svc/sandboxes → 200
TASK-SVC-021  tenant_resources.go           → /svc/tenant/members → 200
TASK-CORE-001 branding_resources.go         → /api/v1/branding → 200
TASK-CORE-002 task_resources.go             → /api/v1/tasks/xxx → 200/404

【第二批 - 第一批完成后】
TASK-SVC-002~006   Model CRUD 完整实现
TASK-SVC-008~010   InferenceService CRUD 完整实现
TASK-SVC-012~013   KnowledgeBase CRUD 完整实现
TASK-SVC-018       GPU容器高级接口
TASK-SVC-020       Sandbox高级接口

【第三批 - 依赖数据管道就绪】
TASK-SVC-014~016   文档上传 + 知识库问答 + SSE 流

【第四批 - 依赖 InferenceService 上线】
TASK-CORE-003      OpenAI 兼容代理 /v1/chat/completions
```

---

## 附 C：常见问题

**Q: handler 里现在要不要对接真实的 model-service / kb-service？**  
A: 第一批不需要。先返回 `{"items":[]}` 让接口通过 curl 验收即可。真实下游对接在第二批完成，届时对应的微服务（model-service、kb-service 等）需要独立开发并在 `MODEL_SERVICE_ADDR` 等 env var 中配置地址。

**Q: make validate-architecture 提示 import 错误怎么办？**  
A: 检查新文件的 import，移除 `pkg/adapters`、`pkg/ports` 的 import。

**Q: stubs.go 里的 `notImplemented` 函数本身要不要删？**  
A: 不要删，其他还未实现的路由还在用它。只删除具体的 `registerXxx` 函数定义（把它移到新文件里）。

**Q: TASK-SVC-017（GPU容器）的路由注册在哪里？**  
A: 需要在 `router.go` 的 `RegisterWithOptions` 里手动添加 `registerGpuContainers(svc)` 调用（参考旁边的 `registerModels(svc)` 写法）。Sandbox 和租户管理同理。
