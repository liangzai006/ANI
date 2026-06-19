# Sprint 13 切片 07 — instance observability Prometheus real provider 就绪声明

> 记录类型：Per-slice readiness（ANI-06「真实底座组件引入强制门禁」§153 的执行前声明）
> 工件归属：Sprint 13 / Core real provider 与 live gate 收敛
> 执行地图：[`sprint13-real-provider-readiness-plan.md`](sprint13-real-provider-readiness-plan.md)
> 状态：**code+contract ready, LIVE PENDING**（A 轨已完成；尚未跑通真实 live gate）。在 evidence 产出前，instance observability 只可标 Tier1 local profile / dev_profile。

---

## 0. 已核对的真实事实（禁止臆测）

1. Sprint 12 已落地 instance observability Core API contract：`listInstanceLogs`、`listInstanceEvents`、`getInstanceMetrics`、`createInstanceExecSession` 与 `listInstanceSecurityEvents` 均在 `demo_instances.go` 经 `ports.InstanceObservability` 暴露。
2. `ports.InstanceObservability` 已存在 logs/events/metrics/security-events/exec session 边界；Gateway handler 不泄漏 Kubernetes、kubelet、Prometheus 或 terminal provider SDK 对象。
3. OpenAPI 已定义对应响应 schema；列表响应保持 `{items,total,next_cursor}`，exec session POST 保留 `idempotency_key`，RBAC scope 保持 `scope:instances:read` / `scope:instances:exec`。
4. S07 A 轨只允许新增 Prometheus + Kubernetes API adapter、fake/mock 单测、契约级 live-gate 和文档闭环；不部署 Prometheus，不执行真实 kubelet/Kubernetes/Prometheus live gate，不标 runtime ready。

## 1. §153 五项声明

| 项 | 内容 |
|---|---|
| **当前状态** | contract + Tier1 local profile；Gateway 默认仍使用 local instance observability profile。A 轨已新增 `PrometheusInstanceObservability` adapter，并在 `INSTANCE_OBSERVABILITY_PROVIDER=prometheus_kubernetes` 显式配置时可注入 bootstrap capabilities；响应 `dev_profile.real_provider=false`。 |
| **真实组件 + 版本** | Prometheus + Kubernetes API / kubelet-backed pod logs/events/metrics；具体 Prometheus 版本、endpoint、Kubernetes API credential、pod/instance label 策略与 exec proxy 策略需 B 轨执行前在真实 lab 只读确认。 |
| **live gate 命令** | 本地契约：`make validate-demo-instances validate-instance-observability-live-gate`；真实 B 轨：`python scripts/validate_instance_observability_live_gate.py --live --evidence-output <path>` 的执行仍为 human-gated，需先人工确认 Prometheus/Kubernetes endpoint 与凭据来源。 |
| **evidence 输出路径** | `repo/development-records/sprint13-instance-observability-prometheus-live-result.md` + 非敏感 evidence JSON；不得归档 bearer token、kubeconfig、Prometheus credential、完整 WebSocket token 或敏感日志 payload。 |
| **失败边界（不得声称）** | 若 logs/events/metrics/security-events/exec session 未在真实 Prometheus + Kubernetes API / kubelet 后端跑通并归档 evidence，不得标 real-provider / runtime ready / production ready；不得用 local synthetic dev_profile 替代 live evidence。 |

## 2. 代码边界

- A 轨新增 `pkg/adapters/runtime/PrometheusInstanceObservability`，实现既有 `ports.InstanceObservability`，不改 port 接口签名，不改 Gateway handler，不新增 `/api/v1/svc`。
- adapter 使用 Kubernetes API 读取 pod logs/events，把 Warning event 投影为 security event；使用 Prometheus HTTP query API 读取 pod-scoped metrics；exec session 仅返回短 TTL Core WebSocket URL，不暴露长期凭据。
- `pkg/bootstrap` 仅在 `INSTANCE_OBSERVABILITY_PROVIDER=prometheus_kubernetes` 显式配置时构造并注入 adapter；默认 dev/local profile 不变，避免把未配置 adapter 误标为 runtime ready。

## 3. 真实服务器安全

- A 轨不部署 Prometheus，不创建/修改真实 Kubernetes 资源，不执行 kubectl/helm/apply，不访问真实 kubelet 或 Prometheus endpoint。
- B 轨执行前必须由人工确认 Prometheus endpoint、Kubernetes API host、credential 来源、tenant namespace 映射、pod label 策略、exec proxy 方案和 evidence 输出路径；凭据不得写入可提交文件或回复。

## 4. 完成判定（A 轨）

```bash
cd repo && make test && make validate-demo-instances validate-instance-observability-live-gate && python scripts/validate_yaml.py api/openapi/v1.yaml && make validate-doc-entrypoints && git diff --check
```

## 5. 关联文档

- Sprint 13 执行地图：[`sprint13-real-provider-readiness-plan.md`](sprint13-real-provider-readiness-plan.md)
- 当前冲刺入口：[`../CURRENT-SPRINT.md`](../CURRENT-SPRINT.md)
- S07 A 轨记录：[`sprint13-instance-observability-prometheus-a-track.md`](sprint13-instance-observability-prometheus-a-track.md)
- 代码：`pkg/ports/instance_observability.go`、`pkg/adapters/runtime/prometheus_instance_observability.go`、`pkg/bootstrap/deps.go`、`services/ani-gateway/internal/router/demo_instances.go`
