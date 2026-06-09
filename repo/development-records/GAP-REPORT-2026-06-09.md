# ANI Services API GAP 分析报告

**生成日期**: 2026-06-09  
**分析范围**: `repo/api/openapi/v1.yaml`、`repo/api/openapi/services/v1.yaml`、`repo/services/ani-services.html`  
**分析目的**: 识别 HTML 产品功能定义与 YAML API 契约之间的差距，生成工作量输入

---

## 数据基线

| 来源 | 总条目 | 已实现 | Stub/缺失 |
|------|--------|--------|---------|
| Core `v1.yaml` | 88 paths | 59 (67%) | 29 stubs |
| Services `services/v1.yaml` | 21 paths | 0 (0%) | 21 stubs |
| `ani-services.html` | 108 接口 | — | — |

---

## A. HTML有、两个YAML均无（需新增 services/v1.yaml 路径）

### A-1. GPU容器模块（10条接口，全部缺失）

| HTML 定义的接口 | 建议 YAML 路径 | HTTP 方法 |
|---------------|--------------|---------|
| GPU容器列表 | `/gpu-containers` | GET |
| 创建GPU容器 | `/gpu-containers` | POST |
| 获取GPU容器详情 | `/gpu-containers/{id}` | GET |
| 更新GPU容器 | `/gpu-containers/{id}` | PATCH |
| 删除GPU容器 | `/gpu-containers/{id}` | DELETE |
| GPU容器监控指标 | `/gpu-containers/{id}/metrics` | GET |
| GPU容器版本历史 | `/gpu-containers/{id}/versions` | GET |
| GPU容器回滚 | `/gpu-containers/{id}/rollback` | POST |
| 可用GPU查询 | `/gpu-containers/available-gpus` | GET |
| GPU容器重建 | `/gpu-containers/{id}/rebuild` | POST |

**注**：全部10条需新增到 `services/v1.yaml`，前缀为 `/api/v1/svc/`。

### A-2. Sandbox模块（11条接口，全部缺失）

| HTML 定义的接口 | 建议 YAML 路径 | HTTP 方法 |
|---------------|--------------|---------|
| Sandbox列表 | `/sandboxes` | GET |
| 创建Sandbox | `/sandboxes` | POST |
| 获取Sandbox详情 | `/sandboxes/{id}` | GET |
| 更新Sandbox | `/sandboxes/{id}` | PATCH |
| 删除Sandbox | `/sandboxes/{id}` | DELETE |
| 延期Sandbox | `/sandboxes/{id}/extend` | POST |
| 暂停Sandbox | `/sandboxes/{id}/pause` | POST |
| 安全事件列表 | `/sandboxes/{id}/security-events` | GET |
| 安全概览 | `/sandboxes/{id}/security-overview` | GET |
| Sandbox扩展配置（列表） | `/sandboxes/{id}/extensions` | GET |
| Sandbox扩展配置（添加） | `/sandboxes/{id}/extensions` | POST |

**注**：全部11条需新增到 `services/v1.yaml`，前缀为 `/api/v1/svc/`。

### A-3. 设置-租户管理（8条接口，大部分缺失）

| HTML 定义的接口 | 建议 YAML 路径 | HTTP 方法 | 归属层 |
|---------------|--------------|---------|-------|
| 成员列表 | `/tenant/members` | GET | services |
| 邀请成员 | `/tenant/members` | POST | services |
| 移除成员 | `/tenant/members/{id}` | DELETE | services |
| 角色列表 | `/tenant/roles` | GET | services |
| SSO配置查询 | `/tenant/sso` | GET | services |
| SSO配置更新 | `/tenant/sso` | PUT | services |
| Webhook列表 | `/tenant/webhooks` | GET | services |
| Webhook管理 | `/tenant/webhooks` | POST | services |

**注**：APIKey管理（7条）已在 Core `v1.yaml` `/auth/api-keys` 实现，不需重复。

---

## B. HTML有、YAML有但全是Stub（需写Handler）

### B-1. Services stubs（`services/v1.yaml` 全部21条，均返回501）

**文件**：`repo/services/ani-gateway/internal/router/stubs.go`

| 路由组 | 路由数 | operationId 范围 |
|--------|--------|----------------|
| Models（`/api/v1/svc/models`） | 7 | listModels, createModel, importModel, getModel, deleteModel, listModelVersions, createModelVersion |
| InferenceServices（`/api/v1/svc/inference-services`） | 5 | listInferenceServices, createInferenceService, getInferenceService, patchInferenceService, deleteInferenceService, getInferenceServiceLogs |
| KnowledgeBases（`/api/v1/svc/knowledge-bases`） | 9 | listKnowledgeBases, createKnowledgeBase, getKnowledgeBase, deleteKnowledgeBase, listKBDocuments, uploadKBDocument, deleteKBDocument, queryKnowledgeBase, streamQueryKnowledgeBase |

**Handler 实现优先级（建议）**：
1. 第一批（无前置依赖，返回空列表即可验通）：listModels, listInferenceServices, listKnowledgeBases
2. 第二批（CRUD骨架）：create/get/delete 各资源
3. 第三批（高级功能）：query、stream、logs

### B-2. Core stubs（在 Core `v1.yaml` 中，5条）

**文件**：`repo/services/ani-gateway/internal/router/stubs.go`

| 路由组 | 路由数 | 路径 |
|--------|--------|------|
| Branding | 3 | GET /branding, PUT /branding, POST /branding/logo |
| Tasks | 2 | GET /tasks/{task_id}, DELETE /tasks/{task_id} |

**注**：Branding 的 GET 路径已在 `isPublicPath()` 中豁免了 auth，Handler 实现无 auth 依赖。

### B-3. OpenAI兼容代理（2条，特殊处理）

| 路由 | 状态 | 说明 |
|------|------|------|
| POST /v1/chat/completions | Stub（inferenceProxy） | 需反代至 vLLM，依赖 InferenceService 就绪 |
| GET /v1/inference/stream | Stub（inferenceProxy） | SSE 流式，依赖 InferenceService 就绪 |

---

## C. YAML有、HTML无（Core基础设施专用，无需在HTML中体现）

以下路径属于 ANI Core 基础设施能力，不是 Services 产品功能，不需要出现在 `ani-services.html`：

- `/k8s-clusters/*`（K8s集群管理）
- `/encryption/*`（加密密钥管理）
- `/secrets`（Secret管理）
- `/vector-stores`（向量存储，Core层）
- `/registry/*`（Harbor镜像仓库）
- `/observability/*`（PromQL代理）

**用量报表**（`/metering/*`）：Core 已实现，HTML 中有"用量报表"模块（5条），需做路径对齐确认（见D类）。

---

## D. 路径语义冲突（HTML 使用了错误前缀）

| HTML 中的错误路径 | 正确路径 | 说明 |
|-----------------|---------|------|
| `/api/v1/console/compute/vms` | `/api/v1/instances` | 虚机是Core层基础设施，前缀为 `/api/v1`，不含 `/console/compute` |
| `/api/v1/console/compute/vms/{id}/disks` | `/api/v1/instances/{id}/...` | 同上，具体子路径需对照 `v1.yaml` instances 相关 operationId |
| GPU容器、Sandbox（无前缀） | `/api/v1/svc/gpu-containers`、`/api/v1/svc/sandboxes` | Services层资源必须用 `/api/v1/svc/` 前缀 |
| 用量报表路径（未确认） | `/api/v1/metering/*` | Core已实现，需确认HTML中的路径是否与YAML一致 |

**虚机模块说明**：`ani-services.html` 的虚机39条接口路径需要全面校对。虚机是 Core 层能力（通过 `registerDemoInstances` 实现，文件 `demo_instances.go` 1140行），Services 通过 Core HTTP API 使用，不需要在 `services/v1.yaml` 中重复定义。

---

## E. Schema缺失（接口存在但响应结构不完整）

| 类型 | 数量 | 影响 |
|------|------|------|
| 只有请求schema、无响应schema | 98/108条 | 前端无法基于YAML生成类型定义 |
| 完整schema（请求+响应均有） | 10/108条 | 主要集中在虚机模块DELETE操作 |
| Services YAML schema缺失类型 | 约20个 | GPU容器、Sandbox等新资源的schema需新建 |

**补全优先级**：新增 GPU容器、Sandbox 的 schema 时一并补全请求和响应，复用现有 `CursorPage`、`ErrorResponse`、`AsyncTask` 组件（已在 `services/v1.yaml` components.schemas 中定义）。

---

## 统计汇总

| 类型 | 数量 | 操作 |
|------|------|------|
| 需新增 services/v1.yaml 路径 | ~29条 | GPU容器10 + Sandbox11 + 租户管理8 |
| 需新增 Handler（已有YAML stub） | 21条 | Services stubs全部 |
| 需修复 Core stubs | 5条 | Branding + Tasks |
| 路径语义冲突（HTML需修正） | ~15条 | 虚机模块全部路径 |
| Schema需补全 | 98条 | 新增资源时一并补全 |
| OpenAI代理（特殊处理） | 2条 | 依赖InferenceService上线 |

---

## 下一步操作（Phase 1-3）

```
Phase 1: HTML←YAML 对齐
  → 修正 repo/services/ani-services.html 中虚机路径前缀错误
     (将 /api/v1/console/compute/vms → /api/v1/instances)
  → 为GPU容器、Sandbox添加正确的 /api/v1/svc/ 前缀
  → 确认用量报表路径与 /api/v1/metering/* 一致

Phase 2: YAML←HTML 扩展
  → 在 repo/api/openapi/services/v1.yaml 新增 A 类缺口路径（~29条）
  → 所有POST/PUT/PATCH添加 idempotency_key

Phase 3: 生成工作量分解
  → 输出 repo/development-records/SERVICES-TEAM-TASKS.md
  → 输出 repo/development-records/CORE-TEAM-TASKS.md
  → 输出 repo/development-records/TASK-DEPENDENCY-MAP.md
```
