# M1-INSTANCE-U-E — VM Volume Binding Local Profile

完成日期：2026-05-19
对应 Sprint：Sprint 2（2026-05-19 提前启动；计划窗口 2026-06-01 ~ 06-15）
验证结果：make test EXIT:0，make validate-core-alpha EXIT:0，make validate-demo-instances EXIT:0，make validate-instance-store EXIT:0，make validate-instance-service EXIT:0，make validate-architecture EXIT:0，git diff --check EXIT:0

## 实现了什么

完成 M1-INSTANCE-U 的第五个可验证切片：VM `attach_volume` / `detach_volume` lifecycle action 在 local/dev profile 中更新实例 `volumes[]` 元数据，不调用 provider executor，不改变实例运行态，并写入 operation timeline。`/api/v1/instances` 响应现在返回 `volumes[]`，`POST /instances/{id}/lifecycle` 可通过 `volume_id` 指定绑定或解绑的数据盘。

## 关键文件改动

| 文件 | 新增/修改 | 说明 |
|---|---|---|
| `pkg/ports/workload_runtime.go` | 修改 | `WorkloadInstanceService` 增加 `AttachVolume` / `DetachVolume` 方法 |
| `pkg/adapters/runtime/instance_service.go` | 修改 | 本地 profile 执行 VM volume attach/detach、precheck、timeline 和 storage 元数据更新 |
| `services/ani-gateway/internal/router/demo_instances.go` | 修改 | lifecycle 支持 `attach_volume` / `detach_volume`，响应返回 `volumes[]` |
| `api/openapi/v1.yaml` | 修改 | `InstanceRecord.volumes` 与 `InstanceLifecycleRequest.volume_id` 已进入 Core Alpha 契约 |
| `scripts/validate_core_alpha_contract.py` | 修改 | 合同守卫覆盖 volume lifecycle handler 和 service 方法 |
| `pkg/adapters/runtime/instance_service_test.go` | 修改 | 覆盖 VM attach/detach 不调用 provider、保持 running、写入 timeline |
| `services/ani-gateway/internal/router/demo_instances_test.go` | 修改 | 覆盖 demo service VM volume binding 响应 |

## 完工标准达成

- [x] `attach_volume` / `detach_volume` lifecycle action 进入 VM local/dev profile
- [x] 数据盘绑定元数据体现在 `InstanceRecord.volumes[]`
- [x] 绑定/解绑操作写入 operation timeline，并与幂等语义保持一致
- [x] Gateway/API response 返回 `volumes[]`
- [x] `make test` 通过
- [x] `make validate-architecture` 通过

## 备注

本切片完成 Core API Alpha 可依赖的 VM 磁盘绑定本地 profile；provider-native 数据盘热插拔执行留给 real provider beta 路径继续对齐。
