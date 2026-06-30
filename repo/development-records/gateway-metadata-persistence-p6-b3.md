# GATEWAY-METADATA-PERSISTENCE-P6-B3

> 记录类型：Feature batch / Gateway metadata persistence（阶段 B · B3）
> 完成日期：2026-06-30
> 范围：Harbor robot pull secret → Kubernetes `imagePullSecrets` 注入（经 port，不经 handler 直调 K8s SDK）

## 目标

在 B1/B2 registry live gate 之上，打通 **Harbor robot 凭据创建** 与 **Kubernetes dockerconfigjson Secret 注入** 的最小产品闭环：Gateway handler 调用 `RegistryPullSecretKubernetesApply` port，由 adapter 组合 `RegistryPullSecretCredentialSource` + `SecretProviderApply`。

## 实现

- **OpenAPI**：`POST /registry/projects/{project}/pull-secret/kubernetes-apply`；响应 `RegistryPullSecretKubernetesApply`（不含 robot 密码明文）。
- **ports**：`RegistryPullSecretCredentialSource`、`RegistryPullSecretKubernetesApply`；`SecretProviderApplyRequest` 增加可选 `Namespace`。
- **Harbor adapter**：`createRobotWithCredentials` 捕获 Harbor 201 响应中的 `secret`；`CreatePullSecretCredential`。
- **runtime adapter**：`RegistryPullSecretKubernetesApplyService` 构建 `.dockerconfigjson` 并经 `KubernetesSecretProviderAdapter` 注入。
- **Gateway**：`registry_pull_secret_runtime.go` 在 `REGISTRY_PROVIDER=harbor` + `SECRET_PROVIDER_MODE=kubernetes_rest` 时接线。
- **live gate**：`run_registry_harbor_live_gate.py`（`--track pull-secret-kubernetes` + `--dev` 一键 orchestration）。
- **契约 gate**：`make validate-gateway-metadata-p6-b3`。
- **S08 proof_items** 扩展：`production_registry_pull_secret_kubernetes_applied`。

## Live gate（人工执行）

### 路径 A — 本机 dev Gateway（推荐，与 B1/B2 一致）

与 `m1-secrets-live-c` 相同：Gateway 经 `kubectl proxy` 访问集群 API；`ANI_AUTH_MODE=dev`，无需 bearer token。

```bash
cd repo
make build-gateway

# 1. 填写 Harbor 密码（勿提交仓库）
export HARBOR_PASSWORD='<lab-secret>'
# 或: export HARBOR_PASSWORD_FILE=$HOME/.config/ani/harbor-password

# 2. 一键 runner（含 proxy、Gateway、live gate、kubectl 校验）
python3 scripts/run_registry_harbor_live_gate.py --track pull-secret-kubernetes --dev
```

手动分步（调试时）：

```bash
# 终端 1 — kubectl proxy
kubectl proxy --address=127.0.0.1 --port=18003 --accept-hosts='.*'

# 终端 2 — Gateway（从 repo/.env 加载 DATABASE_URL）
export HARBOR_PASSWORD='<lab-secret>'
ANI_AUTH_MODE=dev \
SECRET_PROVIDER_MODE=kubernetes_rest \
KUBERNETES_API_HOST=http://127.0.0.1:18003 \
KUBERNETES_PROVIDER_FIELD_MANAGER=ani-registry-pull-secret-b3-live-gate \
REGISTRY_PROVIDER=harbor \
REGISTRY_ENDPOINT=docker.kubercon.local \
REGISTRY_USERNAME=admin \
REGISTRY_PASSWORD="$HARBOR_PASSWORD" \
REGISTRY_SECURE=true \
REGISTRY_TLS_INSECURE=true \
DATABASE_URL='postgres://ani:ani_dev_password@localhost:5432/ani?sslmode=disable' \
./bin/ani-gateway

# 终端 3 — live gate
export GATEWAY_URL="http://$(hostname -I | awk '{print $1}'):8080/api/v1"
export TENANT_ID='00000000-0000-0000-0000-000000000001'
export PULL_SECRET_K8S_NAMESPACE="ani-${TENANT_ID}"
export CLEANUP=true
python3 scripts/run_registry_harbor_live_gate.py --track pull-secret-kubernetes

# 验收 — Secret 类型应为 kubernetes.io/dockerconfigjson
kubectl get secret -n "$PULL_SECRET_K8S_NAMESPACE" -l ani.kubercloud.io/secret-id
```

### 路径 B — in-cluster production-shaped Gateway（NodePort 30080）

需先部署/更新 Gateway Deployment（含 `SECRET_PROVIDER_MODE=kubernetes_rest`，见 `sprint13-production-shaped-gateway-deployment.yaml`）并应用 Harbor Secret：

```bash
kubectl apply -f deploy/real-k8s-lab/sprint13-registry-harbor-live.yaml   # 先改 password
kubectl apply -f deploy/real-k8s-lab/sprint13-production-shaped-gateway-deployment.yaml
kubectl create namespace "ani-${TENANT_ID}" --dry-run=client -o yaml | kubectl apply -f -

export ANI_BEARER_TOKEN='<oidc-token>'
export PRODUCTION_SHAPED=true
export GATEWAY_URL="http://<node-ip>:30080/api/v1"
python3 scripts/run_registry_harbor_live_gate.py --track pull-secret-kubernetes --production-shaped
```

### 环境变量速查

| 变量 | 必填 | 说明 |
|------|------|------|
| `HARBOR_PASSWORD` | 是 | Harbor admin 密码 |
| `TENANT_ID` | 否 | Harbor 项目名，默认全零 UUID |
| `PULL_SECRET_K8S_NAMESPACE` | 否 | 注入目标 namespace，默认 `ani-${TENANT_ID}` |
| `PULL_SECRET_K8S_NAME` | 否 | K8s Secret 名，默认 `ani-live-gate-pull-{RUN_ID}` |
| `ANI_BEARER_TOKEN` | in-cluster 时 | `ANI_AUTH_MODE=auth_service` 必填 |
| `GATEWAY_URL` | 否 | 默认本机 `:8080` 或 NodePort `:30080` |

Evidence：`development-records/live-evidence/sprint13-registry-harbor-b3-live-evidence.json`

每次 live run 应使用唯一 `PULL_SECRET_K8S_NAME`（runner 默认带 `RUN_ID`），避免 Harbor robot 409 后无法取回密码。

## 契约验收

```bash
cd repo
make validate-gateway-metadata-p6-b3
```

## 边界

- robot 密码仅在一次创建时可用；重复 robot 名且无密码时返回 409，不尝试猜测凭据。
- API 响应与 PG 均不存储 robot 密码明文。
- live evidence 需 lab 环境人工执行；不标 full platform production ready。
