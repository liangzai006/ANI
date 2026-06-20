# Sprint 13 切片 01 — 网络路由 Kube-OVN real provider 就绪声明（先声明，后接入）

> 记录类型：Per-slice readiness（ANI-06「真实底座组件引入强制门禁」§153 的执行前声明）
> 工件归属：Sprint 13 / Core real provider 与 live gate 收敛
> 执行地图：[`sprint13-real-provider-readiness-plan.md`](sprint13-real-provider-readiness-plan.md)
> 状态：**production-shaped gate passed for S01 network route gate**。已跑通 Gateway create/list + Kube-OVN bottom observation 并归档 evidence；不代表 full platform production ready。

---

## 0. 已核对的真实事实（禁止臆测）

1. Sprint 12 已落地路由契约与本地实现：`ports.NetworkService.CreateRoute/ListRoutes`（`pkg/ports/network_resources.go`），网关 `GET/POST /networks/routes`（`services/ani-gateway/internal/router/network_resources.go`），当前由 in-memory `NetworkService`（`pkg/adapters/runtime/network_service.go`）支撑 = Tier1 local profile。
2. 网络真实 provider 管线：`ports.NetworkProvider`（`DryRun`/`Apply`/`Observe`）+ `KubeOVNNetworkProviderAdapter`（`pkg/adapters/runtime/kubeovn_network_provider.go`）+ `KubernetesNetworkProviderClient`。S01 production-shaped closure 已将 `LocalNetworkService` provider pipeline 从 route-only 提升为 VPC/Subnet/SecurityGroup/LoadBalancer/Route 通用 provider；Gateway runtime 已支持注入 provider-backed `ports.NetworkService`。
3. live gate 入口：`make validate-kubeovn-network-live-gate` → `scripts/validate_kubeovn_network_live_gate.py`(+test)；fixtures 在 `deploy/real-k8s-lab/kubeovn-network-live-gate.yaml`。S01 production-shaped gate 强制 Gateway `POST/GET /networks/routes` create/list，再由 kubectl 观测底层 Kube-OVN 对象与 cleanup。
4. 底座（Sprint 5/11 已部署，三台物理服务器）：Kube-OVN `v1.15.8`、Kubernetes `v1.36.1`、CNI/CoreDNS Ready。

## 1. §153 五项声明

| 项 | 内容 |
|---|---|
| **当前状态** | S01 网络路由 Kube-OVN production-shaped gate passed。默认仍为 Tier1 local profile；显式 `NETWORK_PROVIDER=kubeovn_rest`、`NETWORK_PROVIDER_APPLY_ENABLED=true`、`NETWORK_PROVIDER_USER_ID`、`NETWORK_PROVIDER_PERMISSION_PROOF=rbac-scope:networks.write` 时，VPC/Subnet/Route 等网络资源可进入 Kube-OVN renderer→dry-run(PATCH dryRun=All)→apply→observe；真实 lab 已跑通 Gateway route create/list/observe/cleanup。 |
| **真实组件 + 版本** | Kube-OVN `v1.15.8`，Kubernetes `v1.36.1`（三台物理开发服务器）。 |
| **live gate 命令** | 本地契约：`make validate-kubeovn-network-live-gate`；真实 B 轨：`python scripts/validate_kubeovn_network_live_gate.py --live --cleanup --production-shaped --gateway-url <in-cluster-gateway>/api/v1 --ani-bearer-token <redacted> --tenant-id <tenant> --evidence-output <path>`（执行前人工只读盘点与确认；成功观察后删除临时底层资源）。 |
| **evidence 输出路径** | `repo/development-records/sprint13-netroute-kubeovn-live-result.md` + `repo/development-records/live-evidence/sprint13-netroute-kubeovn-live-evidence.json`。 |
| **失败边界（不得声称）** | 本次 S01 production-shaped gate 已通过，可标 production-shaped acceptance passed；但不得标 full platform production ready，不得声称 Auth/Dex、正式镜像发布/升级、长期 SLA、`instance`/`nat` next hop 映射、外部负载均衡数据面 SLA 或 S05-S07 已完成。 |

## 2. 代码边界（不改 handler、不改 port 签名）

- S01 B 轨已在 Kube-OVN adapter 内新增「路由 → `Vpc.spec.staticRoutes` manifest」渲染，并把 `RenderRoute` 纳入 `ports.NetworkProviderRenderer`；通过 fake provider 单测验证 route manifest 可进入 `DryRun -> Apply -> Observe` provider 管线。Gateway handler 不绕过 port；Gateway runtime 可注入 provider-backed `NetworkService`。未改 Core OpenAPI。
- 当前 renderer 仅支持 `next_hop_type=gateway`，将 `next_hop_id` 作为 `nextHopIP`；`instance`/`nat` 真实映射执行前仍需确认，不得冒充支持。
- **真实执行前必须先确认** Kube-OVN `v1.15.8` 的静态路由表达方式（`Vpc.spec.staticRoutes` 还是 `VpcStaticRoute`/`StaticRoute` CRD），以部署版本的真实 API 为准；若字段不匹配，必须先修正 adapter 与 live-gate contract 再跑 B 轨。
- `NetworkService` route 方法已支持显式 real-mode forwarding，但 provider 执行所需的 user/permission proof 必须由 bootstrap/Gateway runtime 配置提供；本轮不从 request 伪造 proof，不把凭据写入可提交文件。
- K8s/Kube-OVN SDK 只能在 adapter/provider/client 边界（`bounded_direct`），**禁止进 Gateway handler**；新依赖需在 `validate_component_imports` 登记 allowlist + `coupling_level` + 理由。
- 契约：若真实 provider 暴露 local profile 没有的字段，先在 `api/openapi/v1.yaml` **只增可选字段**再实现，保持 v1 兼容。

## 3. 真实服务器安全（Sprint 11 规则继续有效）

- 任何写操作前**重新只读盘点 + 人工确认**预期影响和回滚；优先在临时/隔离 VPC 上验证路由，真实 B 轨必须使用 `--cleanup` 清理临时资源。
- 不动系统盘 / fstab / 默认 StorageClass；不并发重启；凭据只在本机 `local-secrets/`，**绝不写入可提交文件、evidence、日志或回复**。

## 4. 执行提示词（人工 / AI 可直接粘贴）

```text
角色：ANI Core 平台工程师。ANI 是生产级基础设施平台，代码必须严谨、可落地交付。

加载（按序）：CLAUDE.md → ANI-DOCS-INDEX.md → repo/CURRENT-SPRINT.md →
ANI-06-开发计划.md（§0 + §真实底座组件引入强制门禁）→
repo/development-records/sprint13-real-provider-readiness-plan.md →
repo/development-records/sprint13-netroute-kubeovn-readiness.md →
repo/api/openapi/v1.yaml（networks/routes 段）。

分支：feature/sprint12-core-support，不碰 main、不推远端。

切片：Sprint 13 网络路由 Kube-OVN real provider（CORE-SVC-SUPPORT-NETROUTE-LIVE-A）。
目标：把 ports.NetworkService 的 CreateRoute/ListRoutes 在 real 模式接到 Kube-OVN，
经既有 NetworkProvider(DryRun/Apply/Observe)+KubeOVNNetworkProviderAdapter 管线，
不改 Gateway handler、不改 port 签名。

前置（必须先做，禁止臆测）：
1. 在真实 lab 确认 Kube-OVN v1.15.8 的静态路由 API（Vpc.spec.staticRoutes 或 VpcStaticRoute/StaticRoute CRD），以部署版本为准。
2. 在隔离/临时 VPC 上验证，真实 B 轨命令必须带 `--cleanup`；任何写操作前重新只读盘点 + 人工确认。

实现：
- 新增「路由 → Kube-OVN manifest」渲染 + provider 路径接线（与 VPC/Subnet 同构）。
- NetworkService route 方法 real 模式转发到 provider；local 模式保持不变。
- 扩展 scripts/validate_kubeovn_network_live_gate.py(+fixtures) 覆盖 route create/list 的 render→apply→observe，并在真实 B 轨使用 `--cleanup` 删除临时 namespace/Vpc/Subnet/NetworkPolicy/Service。
- 新组件依赖在 validate_component_imports 登记 allowlist+coupling_level+理由；handler 不直接 import SDK。
- 契约差异先改 v1.yaml（只增可选字段）。

完成判定（全绿并贴出输出）：
cd repo && make test && make validate-network-alpha validate-kubeovn-network-live-gate && python scripts/validate_yaml.py api/openapi/v1.yaml && git diff --check
真实 lab 跑 route create/list/observe，输出非敏感 evidence JSON。

收尾：新增 repo/development-records/sprint13-netroute-kubeovn-live-result.md（含 §153 五项实测结果 + 边界），
更新 development-records/README.md、repo/CURRENT-SPRINT.md、ANI-06-开发计划.md §0；
跑通才把网络路由标 real-provider，否则保持 Tier1 local profile。全部提交到 feature/sprint12-core-support。
```

## 5. 关联文档

- Sprint 13 执行地图：[`sprint13-real-provider-readiness-plan.md`](sprint13-real-provider-readiness-plan.md)
- 当前冲刺入口：[`../CURRENT-SPRINT.md`](../CURRENT-SPRINT.md)
- 真实底座门禁：[`../../ANI-06-开发计划.md`](../../ANI-06-开发计划.md) §「真实底座组件引入强制门禁」
- Kube-OVN 历史 live evidence：`m1-network-live-c-kubeovn-real-lab-result.md`、`m1-network-live-d-kubeovn-external-lb-real-lab-result.md`
- 代码：`pkg/ports/network_resources.go`、`pkg/adapters/runtime/kubeovn_network_provider.go`、`pkg/adapters/runtime/network_service.go`、`services/ani-gateway/internal/router/network_resources.go`
