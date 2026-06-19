# Sprint 13 S02 - K8s workloads vCluster A-track

> 记录类型：Sprint 13 A-track completion record
> 日期：2026-06-19
> 范围：ANI Core only
> 状态：code+contract ready, LIVE PENDING

## 目标

把 Sprint 12 已落地的 `listK8sClusterWorkloads` 从 Tier1 local profile 扩展到 vCluster/Kubernetes API 的真实读取代码边界。A 轨只做 adapter 代码、fake 单测、契约级 live-gate 扩展和文档闭环；不执行真实 Helm/kubectl/apply，不把能力标记为 real-provider/runtime/production ready。

## 实现

- `pkg/adapters/runtime/k8s_cluster_proxy_forwarding_service.go`
  - `ListWorkloads` 在 real-provider cluster 且 resolver 可解析目标时，通过既有 proxy target 只读调用 Kubernetes API。
  - 支持 Deployment、StatefulSet、DaemonSet、Job、CronJob 列表路径，映射到 `ports.K8sClusterWorkloadRecord`。
  - 保持 local profile 不变；非 real-provider cluster 仍委托 `localK8sClusterService`。
  - resolver 身份不匹配、cluster 非 running、Kubernetes API 非 2xx、JSON 非法或 unsupported kind 均 fail closed。
- `pkg/adapters/runtime/k8s_cluster_proxy_forwarding_service_test.go`
  - 新增 fake HTTP round tripper 单测，验证 real-provider workload list 会请求 `/apis/apps/v1/namespaces/default/deployments`，携带 bearer token，并解析 Deployment replicas/ready/image/status。
- `scripts/validate_vcluster_live_gate.py`
  - vCluster live gate 契约新增 `core-workloads-list`，live 模式在 Core cluster register 与 proxy `/version` 后，只读调用 `GET /k8s-clusters/{id}/workloads?namespace=default&kind=Deployment`。
  - evidence JSON 增加 `workloads_status` 与 `workload_count`，不记录 token、IP 或 workload 敏感内容。
- `deploy/real-k8s-lab/vcluster-live-gate.yaml`
  - 增加 `core-workloads-list` contract check。

## 边界

- 未修改 `ports.K8sClusterService` 签名。
- 未修改 Gateway handler。
- 未新增 `/api/v1/svc`。
- 未引入 Kubernetes SDK；通过标准 HTTP/JSON 复用既有 proxy target resolver。
- 未执行真实集群写操作或真实 live gate。

## 验证

本批次已执行：

```bash
cd repo && make test && make validate-core-alpha validate-vcluster-live-gate && python scripts/validate_yaml.py api/openapi/v1.yaml && make validate-doc-entrypoints && git diff --check
```

关键输出：

```text
✅ architecture guardrails valid
✅ Auth Gateway/API contract valid
PASS
ok   github.com/kubercloud/ani/pkg/adapters/runtime
ok   github.com/kubercloud/ani/services/ani-gateway/internal/router
core alpha contract valid
✅ Core API Alpha contract valid
M1-K8S-LIVE-A contract valid; use --live with ANI_GATEWAY_URL and ANI_BEARER_TOKEN
Ran 27 tests in 0.049s
OK
✅ M1-K8S-LIVE-A vCluster live validation gate valid
validated 1 YAML files
document entrypoint boundaries valid
✅ document entrypoints valid
git diff --check: no output
```

## 后续 B 轨结果

S02 B 轨已在 2026-06-20 完成，结果见 `sprint13-k8s-workloads-vcluster-live-result.md`，evidence 见 `live-evidence/sprint13-k8s-workloads-vcluster-live-evidence.json`。本 A-track 记录保留当时的 code+contract ready 事实，不再作为当前状态来源。
