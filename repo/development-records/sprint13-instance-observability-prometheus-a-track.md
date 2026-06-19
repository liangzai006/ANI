# Sprint 13 S07 - instance observability Prometheus A-track

> 记录类型：Sprint 13 A-track completion record
> 日期：2026-06-19
> 范围：ANI Core only
> 状态：code+contract ready, LIVE PENDING
> 批次标识：SPRINT13-INSTANCE-OBSERVABILITY-PROMETHEUS-A-TRACK

## 目标

把 Sprint 12 已落地的 instance observability 从 Tier1 local profile 扩展到 Prometheus + Kubernetes API / kubelet-backed signals 的真实 provider contract 代码边界。A 轨只做 adapter 代码、fake/mock 单测、契约级 live-gate 和文档闭环；不部署 Prometheus、不访问真实 Kubernetes API、不跑真实 live gate。

## 实现

- `pkg/adapters/runtime/prometheus_instance_observability.go`
  - 新增 `PrometheusInstanceObservability`，实现既有 `ports.InstanceObservability`。
  - `ListLogs` 读取 Kubernetes Pod log API，按 level/limit 做 Core schema 映射。
  - `ListEvents` 读取 Kubernetes events API，映射 event id/type/reason/message/count/timestamp。
  - `GetMetrics` 通过 Prometheus `/api/v1/query` 读取 pod-scoped metric sample，返回 `InstanceMetricsRecord`。
  - `ListSecurityEvents` 将 Kubernetes Warning event 投影为 `kubernetes_warning` security event。
  - `CreateExecSession` 返回短 TTL Core WebSocket URL，并按 `idempotency_key` 幂等；不返回长期 token。
- `pkg/bootstrap/deps.go` / `pkg/bootstrap/server.go`
  - 新增显式 `INSTANCE_OBSERVABILITY_PROVIDER=prometheus_kubernetes` 配置路径，构造并注入 `Capabilities.InstanceObservability`。
  - 默认配置保持 `LocalInstanceObservabilityService` dev_profile，不把 contract adapter 标为 runtime ready。
- `deploy/real-k8s-lab/instance-observability-live-gate.yaml`
  - 新增 `SPRINT13-INSTANCE-OBSERVABILITY-PROMETHEUS-A` live gate contract。
- `scripts/validate_instance_observability_live_gate.py`
  - 新增 contract validator，固定 Prometheus readiness、Core logs/events/metrics/security-events/exec session 六个 check；`--live` 保持 human-gated，不在 A 轨自动执行。

## 边界

- 未修改 `ports.InstanceObservability` 签名。
- 未修改 Gateway handler。
- 未新增 `/api/v1/svc`。
- 未执行真实服务器/集群写操作。
- 未把 instance observability 标记为 real-provider/runtime/production ready。

## 验证

已执行 TDD 定向红绿验证：

```text
TestPrometheusInstanceObservabilityListsLogsEventsAndSecurityEvents PASS
TestPrometheusInstanceObservabilityGetsMetricsFromPrometheus PASS
TestPrometheusInstanceObservabilityCreatesIdempotentShortLivedExecSession PASS
TestNewCapabilitiesCanWirePrometheusInstanceObservabilityProvider PASS
InstanceObservabilityLiveGateTest: Ran 6 tests OK
```

已执行最终 A 轨门禁：

```bash
cd repo && make test && make validate-demo-instances validate-instance-observability-live-gate && python scripts/validate_yaml.py api/openapi/v1.yaml && make validate-doc-entrypoints && git diff --check
```

关键输出：

```text
component import guard passed
auth gateway contract valid
PASS
TestPrometheusInstanceObservabilityListsLogsEventsAndSecurityEvents PASS
TestPrometheusInstanceObservabilityGetsMetricsFromPrometheus PASS
TestPrometheusInstanceObservabilityCreatesIdempotentShortLivedExecSession PASS
TestNewCapabilitiesCanWirePrometheusInstanceObservabilityProvider PASS
staged instance demo API valid
SPRINT13-INSTANCE-OBSERVABILITY-PROMETHEUS-A contract valid; live execution is human-gated
Ran 6 tests in 0.009s
OK
validated 1 YAML files
document entrypoint boundaries valid
git diff --check passed
```

## 后续 B 轨

人工确认真实 Prometheus endpoint、Kubernetes API host、credential 来源、tenant namespace 映射、pod/instance label 策略、exec proxy 方案和 evidence 输出路径后，执行 human-gated live gate 并归档非敏感 evidence。真实 evidence 归档前，S07 保持 Tier1 local profile / dev_profile / LIVE PENDING。
