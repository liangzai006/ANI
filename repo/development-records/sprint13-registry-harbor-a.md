# SPRINT13-REGISTRY-HARBOR-A — 镜像仓库 Harbor 真实 provider 对接（代码级，live gate pending）

完成日期：2026-06-26
对应 Sprint：Sprint 13（Core real provider 与 live gate 收敛）
验证结果：`go build ./...`（各 workspace 模块）、`go test`（pkg / ani-gateway / auth-service / reconcile-worker / task-service / cli）、`python3 scripts/validate_component_imports.py --root .`、`make validate-registry-harbor-live-gate`、`git diff --check` 均为 EXIT 0

> 边界声明：本批次只完成**代码级真实 provider 对接**，使用 `httptest` mock Harbor v2.0 API 做单元验证。**未对真实 Harbor 执行 live gate**，因此不标 real-provider runtime ready、不标 production ready。`dev_profile.real_provider=true` 仅表示该 adapter 走真实 Harbor REST 调用路径，不代表已通过真实环境门禁。

## 实现了什么

在既有 `ports.ImageRegistry` 契约（`M1-REGISTRY-A` 已落地，`/registry/*` Core API 不变）下，新增 Harbor v2.0 真实 provider 实现并接入 provider 选择装配：

- 新增 `HarborImageRegistry` adapter，手写 HTTP（HTTP Basic Auth + `pkg/adapters/resilience` 超时/重试/错误分类），对接 Harbor v2.0 REST API：
  - 项目：`EnsureProject` / `CreateProject` / `ListProjects`（`GET/POST /api/v2.0/projects`，409 视为幂等成功）
  - 仓库 / artifact：`ListRepositories` / `ListArtifacts`（仓库名按 Harbor 约定双重 URL 编码，artifact 带 `with_scan_overview`）
  - 扫描：`GetScanResult` / `GetProjectScanReport`（解析 `scan_overview` 的 `scan_status` 与 `summary.summary` 严重度计数；项目报告按仓库/artifact 聚合）
  - 凭证 / 权限：`CreatePullSecret` / `SetRepositoryPermission`（映射到 Harbor 项目级 robot account，201→active、409→duplicate，与本地 profile 幂等语义一致）
  - 兼容方法：`ListTags` / `GetScanStatus`
- 凭据只留在 adapter 边界内，不回传调用方（`RegistryPullSecret` 只返回引用，不含 secret 值），不向 handler/domain 泄漏 Harbor 类型。

## 关键文件改动

| 文件 | 新增/修改 | 说明 |
|---|---|---|
| `pkg/adapters/registry/harbor_image_registry.go` | 新增 | Harbor v2.0 真实 provider adapter |
| `pkg/adapters/registry/harbor_image_registry_test.go` | 新增 | httptest mock Harbor 覆盖项目/仓库/artifact/扫描/robot 幂等/错误映射 |
| `pkg/bootstrap/server.go` | 修改 | Config 增加 `REGISTRY_PROVIDER/ENDPOINT/USERNAME/PASSWORD/SECURE` 字段与 env 覆盖 |
| `pkg/bootstrap/deps.go` | 修改 | 新增 `imageRegistryAdapter` 选择器（local 默认 / not_configured / harbor），装配 `Capabilities.ImageRegistry` |
| `services/ani-gateway/registry_runtime.go` | 新增 | Gateway `REGISTRY_PROVIDER` 选择器，默认返回 nil 让 router 保持本地 profile |
| `services/ani-gateway/registry_runtime_test.go` | 新增 | Gateway registry 选择器 + env 解析单测 |
| `services/ani-gateway/internal/router/router.go` | 修改 | `RegisterOptions` 增加 `ImageRegistry`，`/registry/*` 改走可注入 provider |
| `services/ani-gateway/internal/router/registry_resources.go` | 修改 | `registerHarborWithService` 支持注入 provider，nil 回退本地 profile |
| `services/ani-gateway/main.go` | 修改 | 从 env 装配 image registry provider 并注入 router |
| `deploy/real-k8s-lab/registry-harbor-live-gate.yaml` | 新增 | live gate 契约 YAML（contract 态，LIVE PENDING） |
| `scripts/validate_registry_harbor_live_gate.py` | 新增 | live gate 校验器（contract + `--live` 人类门禁入口） |
| `scripts/validate_registry_harbor_live_gate_test.py` | 新增 | live gate 契约与 mock live 单测 |
| `Makefile` | 修改 | 新增 `validate-registry-harbor-live-gate` target |

## 完工标准达成

- [x] 不改 Core OpenAPI / SDK：复用 `M1-REGISTRY-A` 契约与 `ports.ImageRegistry`
- [x] Harbor 细节限制在 `pkg/adapters/registry/` 内，未引入 provider SDK，通过 `validate_component_imports`
- [x] 默认 local profile 行为保持不变；`REGISTRY_PROVIDER=harbor` 时切换真实 provider
- [x] adapter 层 httptest 单测 + Gateway 选择器单测分层覆盖
- [x] `go build`/`go test`/架构 import guard/`make validate-registry-harbor-live-gate`/`git diff --check` 通过

## Live gate 入口

契约校验（默认，不触达真实 Harbor）：

```bash
cd repo && make validate-registry-harbor-live-gate
```

人类门禁 live 执行（需审批后的真实 Gateway + Harbor + `REGISTRY_PROVIDER=harbor`）：

```bash
cd repo && python3 scripts/validate_registry_harbor_live_gate.py \
  --live \
  --production-shaped \
  --gateway-url https://<gateway>/api/v1 \
  --ani-bearer-token <token> \
  --harbor-url https://<harbor> \
  --harbor-username <user> \
  --harbor-password <password> \
  --tenant-id <tenant> \
  --evidence-output development-records/live-evidence/sprint13-registry-harbor-live-evidence.json
```

可选：`--repository` / `--scan-image` 在 Harbor 已有镜像时追加 artifact list 与 scan-result 检查。

## 未完成 / 后续

- live gate 契约与 `--live` 入口已就绪，但**真实 Harbor B 轨 execution + 脱敏 evidence JSON 未产出**；真实镜像推拉、robot secret 注入 K8s、真实扫描报告回读需人工审批后执行。
- `GetProjectScanReport` 当前按仓库 + artifact 聚合，真实大项目下的分页与调用量需在 live gate 阶段评估。
- 本批次未新增 REAL-K8S-LAB guard，未触碰 Services 冻结目录。
