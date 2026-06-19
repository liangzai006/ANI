# CORE-SVC-SUPPORT-OBSERVABILITY-A — Core Services 支撑观测 Handler

> 批次类型：Feature batch
> 完成日期：2026-06-19
> 范围：仅 ANI Core，Tier1 local profile

## 背景

Sprint 12 目标是闭合 `api/openapi/v1.yaml` 已声明但网关尚未实现的 Core handler 缺口。本批覆盖 B1：实例可观测 5 个 operationId 与 GPU / Sandbox catalog 3 个 operationId。

## 完成内容

- 实现 `listInstanceLogs`、`listInstanceEvents`、`getInstanceMetrics`、`listInstanceSecurityEvents`、`createInstanceExecSession`，handler 落在 `services/ani-gateway/internal/router/demo_instances.go`。
- 新增 `ports.InstanceObservability` 与 `runtime.NewLocalInstanceObservabilityService()`，返回 dev/local 合成日志、事件、指标、安全事件和短期 exec WebSocket URL；exec session 支持 `idempotency_key`，不返回长期凭据。
- 新增 `runtime.NewLocalGPUInventory()` 实现既有 `ports.GPUInventory.ListNodeClasses` / `GetNodeClass` / `PlanScheduling`，供 GPU 清单与 occupancy handler 复用。
- 新增 `ports.SandboxTemplateCatalog` 与 `runtime.NewLocalSandboxTemplateCatalog()`，提供静态/local sandbox 模板 catalog。
- 新增 `services/ani-gateway/internal/router/gpu_inventory_resources.go` 并在 `router.go` 注册：
  - `GET /api/v1/gpu-inventory`
  - `GET /api/v1/gpu-inventory/occupancy`
  - `GET /api/v1/sandbox-templates`
- 所有新响应带 `dev_profile`，明确 `real_provider=false`；本批不声明 real-provider、runtime ready 或 production ready。
- 后续契约对齐补丁：补齐 `api/openapi/v1.yaml` 中 B1 response schema 的 `dev_profile`、列表 `total` 与 GPU/Sandbox item `dev_profile` 字段，并在 `scripts/validate_core_alpha_contract.py` 增加 B1 schema 字段回归检查。

## 验证

TDD 红测先行：

```bash
go test ./pkg/adapters/runtime ./services/ani-gateway/internal/router
```

红测阶段失败原因是缺少 `InstanceObservability` / local GPU inventory / sandbox template catalog / handler 转换函数；实现后 targeted tests 通过。

完整门禁与 curl smoke 结果见本批提交记录和最终执行输出。

## 关键文件

- `pkg/ports/instance_observability.go`
- `pkg/ports/sandbox_template_catalog.go`
- `pkg/ports/gpu_inventory.go`
- `pkg/adapters/runtime/local_instance_observability_service.go`
- `pkg/adapters/runtime/local_gpu_inventory.go`
- `pkg/adapters/runtime/local_sandbox_template_catalog.go`
- `api/openapi/v1.yaml`
- `scripts/validate_core_alpha_contract.py`
- `services/ani-gateway/internal/router/demo_instances.go`
- `services/ani-gateway/internal/router/gpu_inventory_resources.go`
- `services/ani-gateway/internal/router/router.go`

## 后续真实环境门禁关联

本批只完成 Tier1 local profile。Sprint 13 若推进真实 provider，必须沿用本批已建立的 port/handler 边界：

- 实例观测：从 `ports.InstanceObservability` 接真实 K8s/kubelet/Prometheus adapter，并新增 instance-observability live gate。
- GPU 清单：从既有 `ports.GPUInventory.ListNodeClasses` 接真实 GPU discovery/DCGM/node label adapter，并新增 gpu-inventory live gate。
- Sandbox templates：从 `ports.SandboxTemplateCatalog` 接真实 catalog 来源；未接真实 catalog 前只允许 local profile。

完整 Sprint 13 代码关联计划见 `repo/development-records/sprint13-real-provider-readiness-plan.md`。
