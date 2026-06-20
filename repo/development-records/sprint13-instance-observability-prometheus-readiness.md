# Sprint 13 切片 07 — instance observability Prometheus real provider 就绪声明

> 记录类型：Per-slice readiness（ANI-06「真实底座组件引入强制门禁」§153 的执行前声明）
> 工件归属：Sprint 13 / Core real provider 与 live gate 收敛
> 执行地图：[`sprint13-real-provider-readiness-plan.md`](sprint13-real-provider-readiness-plan.md)
> 状态：**production-shaped gate passed**（A 轨与 B 轨均已完成；历史 LIVE PENDING token 仅作门禁兼容语境）。该结论只代表 S07 组件级 production-shaped acceptance，不代表 full platform production ready。

---

## 0. 已核对的真实事实（禁止臆测）

1. Sprint 12 已落地 instance observability Core API contract：`listInstanceLogs`、`listInstanceEvents`、`getInstanceMetrics`、`createInstanceExecSession` 与 `listInstanceSecurityEvents` 均在 `demo_instances.go` 经 `ports.InstanceObservability` 暴露。
2. `ports.InstanceObservability` 已存在 logs/events/metrics/security-events/exec session 边界；Gateway handler 不泄漏 Kubernetes、kubelet、Prometheus 或 terminal provider SDK 对象。
3. OpenAPI 已定义对应响应 schema；列表响应保持 `{items,total,next_cursor}`，exec session POST 保留 `idempotency_key`，RBAC scope 保持 `scope:instances:read` / `scope:instances:exec`。
4. S07 B 轨已在真实 lab 中部署临时 Prometheus 验证栈，并经 production-shaped Gateway 调用 Core logs/events/metrics/security-events/exec session；evidence 为非敏感 JSON，不包含 token、kubeconfig、节点地址、Prometheus 凭据或 WebSocket token。

## 1. §153 五项声明

| 项 | 内容 |
|---|---|
| **当前状态** | production-shaped gate passed；Gateway 默认仍可使用 local instance observability profile，但 production-shaped deployment 已通过 `INSTANCE_OBSERVABILITY_PROVIDER=prometheus_kubernetes` 显式注入 Prometheus + Kubernetes API adapter。 |
| **真实组件 + 版本** | 临时验证栈使用 Prometheus `prom/prometheus:v2.55.1`，通过 Kubernetes API / kubelet-backed pod logs/events/metrics 读取真实信号；Gateway 使用 in-cluster ServiceAccount 和 production-shaped Auth/Dex。 |
| **live gate 命令** | 本地契约：`make validate-demo-instances validate-instance-observability-live-gate`；真实 B 轨：`python scripts/validate_instance_observability_live_gate.py --live --production-shaped --cleanup --evidence-output development-records/live-evidence/sprint13-instance-observability-prometheus-live-evidence.json`。 |
| **evidence 输出路径** | `repo/development-records/sprint13-instance-observability-prometheus-live-result.md` + `repo/development-records/live-evidence/sprint13-instance-observability-prometheus-live-evidence.json`；未归档 bearer token、kubeconfig、Prometheus credential、完整 WebSocket token 或敏感日志 payload。 |
| **失败边界（不得声称）** | 当前 S07 只可声明组件级 production-shaped acceptance passed；不得据此声明 full platform production ready、长期 Prometheus HA/持久化完成、正式镜像发布完成或平台 SLA/soak 完成。 |

## 2. 代码边界

- A/B 轨新增并验证 `pkg/adapters/runtime/PrometheusInstanceObservability`，实现既有 `ports.InstanceObservability`，不改 port 接口签名，不改 Gateway handler，不新增 `/api/v1/svc`。
- adapter 使用 Kubernetes API 读取 pod logs/events，把 Warning event 投影为 security event；使用 Prometheus HTTP query API 读取 pod-scoped metrics；exec session 仅返回短 TTL Core WebSocket URL，不暴露长期凭据。
- Gateway runtime 仅在 `INSTANCE_OBSERVABILITY_PROVIDER=prometheus_kubernetes` 显式配置时构造并注入 adapter；默认 dev/local profile 不变，避免把未配置 adapter 误标为 runtime ready。

## 3. 真实服务器安全

- B 轨仅部署临时 Prometheus 验证栈与临时 Pod/Event；使用 `--cleanup` 清理临时 Pod/Event，Prometheus 栈为验证用途，不代表长期生产 HA/持久化部署。
- Auth/Dex live gate 密码文件位于 `local-secrets/`，bcrypt hash patch 与 token 获取均未写入 repo/evidence；凭据、节点地址、kubeconfig、bearer token 不得写入可提交文件或回复。

## 4. 完成判定

```bash
cd repo && make test && make validate-demo-instances && make validate-instance-observability-live-gate && make validate-sprint13-b-track-production-shape && python scripts/validate_yaml.py api/openapi/v1.yaml && make validate-doc-entrypoints && git diff --check
```

## 5. 关联文档

- Sprint 13 执行地图：[`sprint13-real-provider-readiness-plan.md`](sprint13-real-provider-readiness-plan.md)
- 当前冲刺入口：[`../CURRENT-SPRINT.md`](../CURRENT-SPRINT.md)
- S07 A 轨记录：[`sprint13-instance-observability-prometheus-a-track.md`](sprint13-instance-observability-prometheus-a-track.md)
- S07 B 轨 live result：[`sprint13-instance-observability-prometheus-live-result.md`](sprint13-instance-observability-prometheus-live-result.md)
- 代码：`pkg/ports/instance_observability.go`、`pkg/adapters/runtime/prometheus_instance_observability.go`、`pkg/bootstrap/deps.go`、`services/ani-gateway/internal/router/demo_instances.go`
