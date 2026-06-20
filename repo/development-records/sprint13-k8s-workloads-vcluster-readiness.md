# Sprint 13 切片 02 — K8s workloads vCluster real provider 就绪声明

> 记录类型：Per-slice readiness（ANI-06「真实底座组件引入强制门禁」§153 的执行前声明）
> 工件归属：Sprint 13 / Core real provider 与 live gate 收敛
> 执行地图：[`sprint13-real-provider-readiness-plan.md`](sprint13-real-provider-readiness-plan.md)
> 状态：**production-shaped gate passed for S02 workload list gate**（B 轨已完成；见 `sprint13-k8s-workloads-vcluster-live-result.md`，`production_shape.status=passed`）。不代表 full platform production ready。

---

## 0. 已核对的真实事实（禁止臆测）

1. Sprint 12 已落地 workload list 契约与本地实现：`ports.K8sClusterService.ListWorkloads`（`pkg/ports/k8s_clusters.go`），网关 `GET /k8s-clusters/{cluster_id}/workloads`（`services/ani-gateway/internal/router/k8s_cluster_resources.go`），当前由 `localK8sClusterService` 返回内置 dev-profile workload。
2. 既有 real vCluster 代码边界：`K8sClusterProviderApply`、`K8sClusterKubeconfigProvider`、`K8sClusterProxyTargetResolver` / `Store`、`NewK8sClusterProxyForwardingService`，以及 `validate-vcluster-live-gate`。Sprint 5 已证明 vCluster Helm/kubeconfig/Core proxy `/version` live gate。
3. S02 A 轨只允许复用既有 proxy target / Kubernetes API 读取路径补 workload list adapter 和契约级 live-gate；不改 `ports.K8sClusterService` 签名，不改 Gateway handler，不新增 `/api/v1/svc`。
4. 真实底座版本：vCluster 运行在 Kubernetes `v1.36.1` lab 之上；历史 live gate 中租户 vCluster 返回 Kubernetes version，真实 workload list 仍需单独 evidence。

## 1. §153 五项声明

| 项 | 内容 |
|---|---|
| **当前状态** | S02 workload list production-shaped gate passed；local profile 仍保留本地模拟路径，真实证据来自 Gateway `/k8s-clusters/{id}/workloads` 经 metadata target TLS 访问 vCluster Kubernetes API observe。 |
| **真实组件 + 版本** | 宿主集群 Kubernetes `v1.36.1`；vCluster Helm chart/app 固定 `0.34.1`；vCluster API evidence 返回 Kubernetes `v1.35.0`；vCluster CLI `v0.34.1`。 |
| **live gate 命令** | 本地契约：`make validate-vcluster-live-gate`；真实 B 轨：`python scripts/validate_vcluster_live_gate.py --live --production-shaped --gateway-url <in-cluster-core-api>/api/v1 --ani-bearer-token <redacted> --chart-version 0.34.1 --evidence-output development-records/live-evidence/sprint13-k8s-workloads-vcluster-live-evidence.json`，覆盖临时 Deployment create、Core proxy `/version`、Core workload list observe 与 cleanup；production-shaped 模式禁止本地 proxy-server。 |
| **evidence 输出路径** | `repo/development-records/sprint13-k8s-workloads-vcluster-live-result.md` + `repo/development-records/live-evidence/sprint13-k8s-workloads-vcluster-live-evidence.json`。 |
| **失败边界（不得声称）** | S02 已通过 workload list production-shaped evidence，但不得标 full platform production ready；不得声称长期 workload 生命周期、跨 namespace 策略、Auth/Dex production gate 或 S03-S07 已完成。 |

## 2. 代码边界

- A 轨优先复用 `NewK8sClusterProxyForwardingService` 和 proxy target resolver，通过 Kubernetes API 只读读取 Deployment/StatefulSet/DaemonSet/Job/CronJob 列表并映射到 `K8sClusterWorkloadRecord`。
- local profile 保持不变；只有 cluster 已由 real provider 创建且 proxy target 可解析时，才尝试真实 workload reader。
- 真实 API 路径和字段必须来自 Kubernetes API 对象结构；不新增 Kubernetes SDK 依赖时无需更新 component import allowlist。
- 失败必须 fail closed：resolver identity 不匹配、API 非 2xx、JSON 非法或不支持 kind 时返回错误，不伪造成功。

## 3. 真实服务器安全

- A 轨不执行 Helm/kubectl apply，不部署或修改真实 vCluster。
- B 轨已由人工确认后执行；凭据未写入可提交文件或回复。

## 4. 完成判定（A 轨）

```bash
cd repo && make test && make validate-core-alpha validate-vcluster-live-gate && python scripts/validate_yaml.py api/openapi/v1.yaml && make validate-doc-entrypoints && git diff --check
```

## 5. 关联文档

- Sprint 13 执行地图：[`sprint13-real-provider-readiness-plan.md`](sprint13-real-provider-readiness-plan.md)
- 当前冲刺入口：[`../CURRENT-SPRINT.md`](../CURRENT-SPRINT.md)
- vCluster 历史 live evidence：`m1-k8s-live-g-vcluster-real-lab-result.md`、`m1-k8s-live-h-vcluster-upgrade-real-lab-result.md`
- S02 A 轨记录：[`sprint13-k8s-workloads-vcluster-a-track.md`](sprint13-k8s-workloads-vcluster-a-track.md)
- 代码：`pkg/ports/k8s_clusters.go`、`pkg/adapters/runtime/local_k8s_cluster_service.go`、`pkg/adapters/runtime/k8s_cluster_proxy_forwarding_service.go`、`services/ani-gateway/internal/router/k8s_cluster_resources.go`
