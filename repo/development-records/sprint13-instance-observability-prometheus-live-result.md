# Sprint 13 S07 - instance observability Prometheus live result

> 记录类型：Sprint 13 B-track production-shaped live result
> 日期：2026-06-21
> 范围：ANI Core only
> 批次标识：SPRINT13-INSTANCE-OBSERVABILITY-PROMETHEUS-LIVE-A
> 状态：production-shaped gate passed

## 目标

证明 Sprint 12 已落地的 Core instance observability handlers 可以经 production-shaped Gateway 调用真实 Prometheus + Kubernetes API / kubelet-backed backend，覆盖 logs、events、metrics、security-events 与 exec session。

## 实现范围

- Gateway runtime 显式配置 `INSTANCE_OBSERVABILITY_PROVIDER=prometheus_kubernetes`。
- `PrometheusInstanceObservability` 复用既有 `ports.InstanceObservability`，未修改 port 签名。
- Router 在 provider 模式下使用 Core instance `name` 作为 Kubernetes pod target，外部 API 仍使用 `instance_id`。
- live gate 使用 production-shaped Auth/Dex bearer，经 Gateway 调用 Core v1 `/instances` 相关 handler。
- 临时 Prometheus 验证栈部署在独立 namespace；临时 target Pod/Event 使用 `--cleanup` 清理。

## Evidence

- JSON：`development-records/live-evidence/sprint13-instance-observability-prometheus-live-evidence.json`
- `production_shape.status=passed`
- `proof_items`：
  - `production_gateway`
  - `production_prometheus_service_or_query`
  - `production_kubelet_or_kubernetes_api_access`

关键非敏感结果：

```text
prometheus_health_status=200
instance_create_status=201
logs_status=200
events_status=200
metrics_status=200
security_events_status=200
exec_status=200
cleanup_status=200
logs_count>=1
events_count>=1
security_events_count>=1
metrics_cpu_present=true
exec_ws_url_present=true
exec_token_exposed=false
```

## Gate

```bash
python scripts/validate_instance_observability_live_gate.py \
  --live \
  --production-shaped \
  --gateway-url <production-shaped-gateway-api> \
  --ani-bearer-token <redacted> \
  --prometheus-url <approved-prometheus-endpoint> \
  --kubeconfig <local-secret-kubeconfig> \
  --evidence-output development-records/live-evidence/sprint13-instance-observability-prometheus-live-evidence.json \
  --cleanup
```

## Boundary

Production-shaped gate passed is not production ready for the full platform。当前 Prometheus 为验证栈，不代表长期 Prometheus HA/持久化、正式镜像发布/升级、备份恢复、长期 SLA/soak 或故障注入已完成。

历史 `LIVE PENDING` token 仅作门禁兼容语境；S07 live evidence 已归档。
