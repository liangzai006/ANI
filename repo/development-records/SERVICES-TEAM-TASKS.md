# Services 团队任务分解

**生成日期**: 2026-06-09  
**基于**: `repo/api/openapi/services/v1.yaml`（Phase 2 扩展后，含 GPU容器/Sandbox/租户管理）  
**执行入口**: `repo/services/ani-gateway/internal/router/`  
**架构约束**: 禁止 import `pkg/adapters`、`pkg/ports`；允许 import `pkg/generated/pb/`

---

## 执行准备

每个 handler 实现必须：
1. 从 `c.MustGet("tenant_id").(string)` 提取租户 ID
2. mutation 操作从 requestBody 读取 `idempotency_key`
3. 错误统一返回 `ErrorResponse` JSON（code + message + request_id）
4. 下游服务地址从 env var 读取（`os.Getenv("MODEL_SERVICE_ADDR")` 等）

---

## TASK-SVC-001: 实现 listModels handler

**Team**: Services  
**YAML 来源**: `services/v1.yaml` operationId=`listModels`  
**Files**:
- 修改: `repo/services/ani-gateway/internal/router/stubs.go` → 移除 `registerModels` 中的 `notImplemented` 调用
- 新建: `repo/services/ani-gateway/internal/router/model_resources.go`

**Handler 逻辑**:
1. 从 `c.MustGet("tenant_id").(string)` 提取租户 ID
2. 解析 query params: `status`、`limit`（default 20）、`cursor`
3. 调用 model-service（`MODEL_SERVICE_ADDR`，default `127.0.0.1:9201`）
4. 返回 `CursorPage[Model]` JSON

**验收命令**:
```bash
curl -H "X-Dev-Tenant-ID: test" http://localhost:8080/api/v1/svc/models
# 期望: 200 + {"items":[], "next_cursor":null}
```
**前置依赖**: 无（可先返回空列表骨架）

---

## TASK-SVC-002: 实现 createModel handler

**Team**: Services  
**YAML 来源**: `services/v1.yaml` operationId=`createModel`  
**Files**: `repo/services/ani-gateway/internal/router/model_resources.go`

**Handler 逻辑**:
1. 提取 `tenant_id`
2. 解析 requestBody（`name`、`display_name`、`capabilities`）
3. 验证 `name` 符合正则 `^[a-z0-9][a-z0-9.-]{0,62}$`
4. 调用 model-service 创建
5. 返回 201 + `Model` JSON

**验收命令**:
```bash
curl -X POST -H "X-Dev-Tenant-ID: test" -H "Content-Type: application/json" \
  -d '{"name":"test-model","display_name":"Test"}' \
  http://localhost:8080/api/v1/svc/models
# 期望: 201 + Model 对象
```
**前置依赖**: TASK-SVC-001（同文件）

---

## TASK-SVC-003: 实现 importModel handler

**Team**: Services  
**YAML 来源**: `services/v1.yaml` operationId=`importModel`  
**Files**: `repo/services/ani-gateway/internal/router/model_resources.go`

**Handler 逻辑**:
1. 提取 `tenant_id`
2. 解析 requestBody（`source`、`repo_id`、`revision`、`idempotency_key`）
3. 验证 `idempotency_key` 非空
4. 提交异步导入任务
5. 返回 202 + `AsyncTask` JSON，设置 `Location` header

**前置依赖**: TASK-SVC-001

---

## TASK-SVC-004: 实现 getModel handler

**Team**: Services  
**YAML 来源**: `services/v1.yaml` operationId=`getModel`  
**Files**: `repo/services/ani-gateway/internal/router/model_resources.go`

**Handler 逻辑**:
1. 从 path param 提取 `model_id`
2. 调用 model-service 查询
3. 若不存在返回 404 ErrorResponse（code: NOT_FOUND）

**前置依赖**: TASK-SVC-001

---

## TASK-SVC-005: 实现 deleteModel handler

**Team**: Services  
**YAML 来源**: `services/v1.yaml` operationId=`deleteModel`  
**Files**: `repo/services/ani-gateway/internal/router/model_resources.go`

**Handler 逻辑**:
1. 从 path param 提取 `model_id`
2. 调用 model-service 删除
3. 返回 204

**前置依赖**: TASK-SVC-004

---

## TASK-SVC-006: 实现 createModelVersion handler

**Team**: Services  
**YAML 来源**: `services/v1.yaml` operationId=`createModelVersion`  
**Files**: `repo/services/ani-gateway/internal/router/model_resources.go`

**Handler 逻辑**:
1. 从 path param 提取 `model_id`，从 body 提取版本元数据
2. 验证 `checksum_sha256` 非空
3. 调用 model-service 创建版本
4. 返回 201 + `ModelVersion` JSON

**前置依赖**: TASK-SVC-004

---

## TASK-SVC-007: 实现 listInferenceServices handler

**Team**: Services  
**YAML 来源**: `services/v1.yaml` operationId=`listInferenceServices`  
**Files**:
- 修改: `repo/services/ani-gateway/internal/router/stubs.go` → 移除 `registerInferenceServices` 中的 `notImplemented`
- 新建: `repo/services/ani-gateway/internal/router/inference_resources.go`

**Handler 逻辑**:
1. 提取 `tenant_id`
2. 调用 inference-service（`INFERENCE_SERVICE_ADDR`）
3. 返回 `{"items": [...]}` JSON

**验收命令**:
```bash
curl -H "X-Dev-Tenant-ID: test" http://localhost:8080/api/v1/svc/inference-services
# 期望: 200 + {"items":[]}
```
**前置依赖**: 无

---

## TASK-SVC-008: 实现 createInferenceService handler

**Team**: Services  
**YAML 来源**: `services/v1.yaml` operationId=`createInferenceService`  
**Files**: `repo/services/ani-gateway/internal/router/inference_resources.go`

**Handler 逻辑**:
1. 解析 requestBody（`name`、`model`、`replicas`、`gpu_type`、`gpu_count_per_pod`）
2. 提交部署任务
3. 返回 202 + `InferenceService` JSON

**前置依赖**: TASK-SVC-007

---

## TASK-SVC-009: 实现 getInferenceService handler

**Team**: Services  
**YAML 来源**: `services/v1.yaml` operationId=`getInferenceService`  
**Files**: `repo/services/ani-gateway/internal/router/inference_resources.go`

**前置依赖**: TASK-SVC-007

---

## TASK-SVC-010: 实现 deleteInferenceService handler

**Team**: Services  
**YAML 来源**: `services/v1.yaml` operationId=`deleteInferenceService`  
**Files**: `repo/services/ani-gateway/internal/router/inference_resources.go`

**Handler 逻辑**: 提交停止删除任务，返回 202。

**前置依赖**: TASK-SVC-009

---

## TASK-SVC-011: 实现 listKnowledgeBases handler

**Team**: Services  
**YAML 来源**: `services/v1.yaml` operationId=`listKnowledgeBases`  
**Files**:
- 修改: `repo/services/ani-gateway/internal/router/stubs.go` → 移除 `registerKnowledgeBases` 中的 `notImplemented`
- 新建: `repo/services/ani-gateway/internal/router/kb_resources.go`

**验收命令**:
```bash
curl -H "X-Dev-Tenant-ID: test" http://localhost:8080/api/v1/svc/knowledge-bases
# 期望: 200 + {"items":[]}
```
**前置依赖**: 无

---

## TASK-SVC-012: 实现 createKnowledgeBase handler

**Team**: Services  
**YAML 来源**: `services/v1.yaml` operationId=`createKnowledgeBase`  
**Files**: `repo/services/ani-gateway/internal/router/kb_resources.go`

**Handler 逻辑**:
1. 解析 requestBody（`name`、`embedding_model`、`chunk_size`、`top_k`）
2. 调用 kb-service（`KB_SERVICE_ADDR`）
3. 返回 201 + `KnowledgeBase` JSON

**前置依赖**: TASK-SVC-011

---

## TASK-SVC-013: 实现 getKnowledgeBase / deleteKnowledgeBase handlers

**Team**: Services  
**YAML 来源**: operationId=`getKnowledgeBase`, `deleteKnowledgeBase`  
**Files**: `repo/services/ani-gateway/internal/router/kb_resources.go`

**前置依赖**: TASK-SVC-011

---

## TASK-SVC-014: 实现 listKnowledgeBaseDocuments / uploadKnowledgeBaseDocument handlers

**Team**: Services  
**YAML 来源**: operationId=`listKnowledgeBaseDocuments`, `uploadKnowledgeBaseDocument`  
**Files**: `repo/services/ani-gateway/internal/router/kb_resources.go`

**注**: uploadDocument 是 multipart/form-data，需用 Hertz 的 `c.FormFile("file")`。

**前置依赖**: TASK-SVC-012（知识库存在才能上传文档）

---

## TASK-SVC-015: 实现 queryKnowledgeBase handler

**Team**: Services  
**YAML 来源**: `services/v1.yaml` operationId=`queryKnowledgeBase`  
**Files**: `repo/services/ani-gateway/internal/router/kb_resources.go`

**Handler 逻辑**:
1. 验证 `idempotency_key` 非空，`question` 长度 1-2000
2. 调用 kb-service RAG 接口
3. 返回 `KBQueryResponse` JSON

**前置依赖**: TASK-SVC-014（需要有索引数据）

---

## TASK-SVC-016: 实现 streamQueryKnowledgeBase handler

**Team**: Services  
**YAML 来源**: `services/v1.yaml` operationId=`streamQueryKnowledgeBase`  
**Files**: `repo/services/ani-gateway/internal/router/kb_resources.go`

**注**: SSE 响应，设置 `Content-Type: text/event-stream`，循环写入 `data: {chunk}\n\n`。

**前置依赖**: TASK-SVC-015

---

## TASK-SVC-017: 实现 GPU容器 CRUD handlers

**Team**: Services  
**YAML 来源**: operationId=`listGpuContainers`, `createGpuContainer`, `getGpuContainer`, `patchGpuContainer`, `deleteGpuContainer`  
**Files**:
- 修改: `repo/services/ani-gateway/internal/router/router.go` → 新增 `registerGpuContainers(svc)` 调用
- 新建: `repo/services/ani-gateway/internal/router/gpu_container_resources.go`

**Handler 逻辑**:
1. `createGpuContainer` 验证 `idempotency_key`，调用 GPU 容器编排服务（`GPU_CONTAINER_SERVICE_ADDR`）
2. `patchGpuContainer` 不需要 idempotency_key（PATCH 语义为幂等）
3. 其余标准 CRUD 模式

**验收命令**:
```bash
curl -H "X-Dev-Tenant-ID: test" http://localhost:8080/api/v1/svc/gpu-containers
# 期望: 200 + {"items":[]}
```
**前置依赖**: 无（先返回空列表）

---

## TASK-SVC-018: 实现 GPU容器高级接口 handlers

**Team**: Services  
**YAML 来源**: operationId=`listAvailableGpus`, `getGpuContainerMetrics`, `listGpuContainerVersions`, `rollbackGpuContainer`, `rebuildGpuContainer`  
**Files**: `repo/services/ani-gateway/internal/router/gpu_container_resources.go`

**前置依赖**: TASK-SVC-017

---

## TASK-SVC-019: 实现 Sandbox CRUD handlers

**Team**: Services  
**YAML 来源**: operationId=`listSandboxes`, `createSandbox`, `getSandbox`, `patchSandbox`, `deleteSandbox`  
**Files**:
- 修改: `repo/services/ani-gateway/internal/router/router.go` → 新增 `registerSandboxes(svc)` 调用
- 新建: `repo/services/ani-gateway/internal/router/sandbox_resources.go`

**Handler 逻辑**: `createSandbox` 验证 `idempotency_key`，调用沙箱编排服务（`SANDBOX_SERVICE_ADDR`）。

**验收命令**:
```bash
curl -H "X-Dev-Tenant-ID: test" http://localhost:8080/api/v1/svc/sandboxes
# 期望: 200 + {"items":[]}
```
**前置依赖**: 无

---

## TASK-SVC-020: 实现 Sandbox 高级接口 handlers

**Team**: Services  
**YAML 来源**: operationId=`extendSandbox`, `pauseSandbox`, `listSandboxSecurityEvents`, `getSandboxSecurityOverview`  
**Files**: `repo/services/ani-gateway/internal/router/sandbox_resources.go`

**注**: `extendSandbox` 和 `pauseSandbox` 需 `idempotency_key`。

**前置依赖**: TASK-SVC-019

---

## TASK-SVC-021: 实现 租户管理 handlers

**Team**: Services  
**YAML 来源**: operationId=`listTenantMembers`, `inviteTenantMember`, `removeTenantMember`, `listTenantRoles`, `getSsoConfig`, `updateSsoConfig`, `listWebhooks`, `createWebhook`, `deleteWebhook`  
**Files**:
- 修改: `repo/services/ani-gateway/internal/router/router.go` → 新增 `registerTenant(svc)` 调用
- 新建: `repo/services/ani-gateway/internal/router/tenant_resources.go`

**Handler 逻辑**:
1. 所有接口校验 `tenant-admin` 角色（`c.MustGet("roles")`）
2. `inviteTenantMember`、`updateSsoConfig`、`createWebhook` 需 `idempotency_key`
3. 调用租户管理服务（`TENANT_SERVICE_ADDR`）

**验收命令**:
```bash
curl -H "X-Dev-Tenant-ID: test" http://localhost:8080/api/v1/svc/tenant/members
# 期望: 200 + {"items":[]}
```
**前置依赖**: 无（可先返回空列表）
