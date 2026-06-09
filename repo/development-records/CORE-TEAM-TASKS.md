# Core 团队任务分解

**生成日期**: 2026-06-09  
**基于**: `repo/api/openapi/v1.yaml` stubs（Branding + Tasks）  
**执行入口**: `repo/services/ani-gateway/internal/router/`  
**注**: Core handler 可以 import `pkg/adapters`（通过依赖注入），但 handler 文件本身不直接 new adapter

---

## TASK-CORE-001: 实现 getBranding / updateBranding / uploadBrandingLogo handlers

**Team**: Core  
**YAML 来源**: `v1.yaml` operationId=`getBranding`, `updateBranding`, `uploadBrandingLogo`  
**Files**:
- 修改: `repo/services/ani-gateway/internal/router/stubs.go` → 移除 `registerBranding` 调用中的 `notImplemented`
- 新建: `repo/services/ani-gateway/internal/router/branding_resources.go`

**Handler 逻辑**:

`getBranding`（GET /branding）：
1. 此路径已在 `isPublicPath()` 中豁免 auth（`middleware/auth.go:90`）
2. 从持久化存储（ConfigMap 或 K8s Secret）读取 branding 配置
3. 返回 Branding schema JSON（company_name, logo_url, theme_color 等）

`updateBranding`（PUT /branding）：
1. 验证 `tenant_id`（admin 操作）
2. 解析 requestBody，更新存储
3. 返回更新后的 Branding JSON

`uploadBrandingLogo`（POST /branding/logo）：
1. 接收 multipart/form-data 图片
2. 存储到对象存储，返回 logo_url
3. 更新 Branding 记录

**验收命令**:
```bash
# getBranding 无需 auth
curl http://localhost:8080/api/v1/branding
# 期望: 200 + branding 对象（不返回 501）

# updateBranding
curl -X PUT -H "X-Dev-Tenant-ID: admin" -H "Content-Type: application/json" \
  -d '{"company_name":"ANI"}' http://localhost:8080/api/v1/branding
# 期望: 200 + branding 对象
```
**前置依赖**: 无

---

## TASK-CORE-002: 实现 getTask / deleteTask handlers

**Team**: Core  
**YAML 来源**: `v1.yaml` operationId=`getTask`, `deleteTask`  
**Files**:
- 修改: `repo/services/ani-gateway/internal/router/stubs.go` → 移除 `registerTasks` 调用中的 `notImplemented`
- 新建: `repo/services/ani-gateway/internal/router/task_resources.go`

**Handler 逻辑**:

`getTask`（GET /tasks/{task_id}）：
1. 从 `c.MustGet("tenant_id").(string)` 提取租户 ID（隔离不同租户的任务）
2. 从 `pkg/ports` AsyncTaskPort 或任务数据库查询任务状态
3. 返回 AsyncTask schema JSON

`deleteTask`（DELETE /tasks/{task_id}）：
1. 验证任务属于当前租户
2. 取消或软删除任务
3. 返回 204

**验收命令**:
```bash
curl -H "X-Dev-Tenant-ID: test" http://localhost:8080/api/v1/tasks/00000000-0000-0000-0000-000000000001
# 期望: 200（若存在）或 404（若不存在），不返回 501
```
**前置依赖**: 无

---

## TASK-CORE-003: 实现 inferenceProxy（OpenAI兼容代理）

**Team**: Core（或 Services 团队接管，依团队分工）  
**YAML 来源**: 无正式 YAML（`/v1/chat/completions` 是 OpenAI 兼容接口）  
**Files**:
- 修改: `repo/services/ani-gateway/internal/router/stubs.go` → 移除 `inferenceProxy` 的 `notImplemented` 调用（保留函数名，更改实现）

**Handler 逻辑**:
1. 从 request body 提取 `model` 字段
2. 根据 model 名称查找对应的 InferenceService endpoint_url
3. 反向代理到 vLLM endpoint（HTTP 代理，转发请求头和 body）
4. 流式响应透传（保持 SSE/chunked）

**注意**: 此接口依赖 InferenceService 上线，优先级最低。建议作为 TASK-SVC-008/009 完成后的收尾任务。

**前置依赖**: TASK-SVC-008（createInferenceService 有数据）、TASK-SVC-009（getInferenceService 能查到 endpoint_url）
