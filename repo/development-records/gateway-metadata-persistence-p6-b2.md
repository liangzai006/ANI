# GATEWAY-METADATA-PERSISTENCE-P6-B2

> 记录类型：Feature batch / Gateway metadata persistence（阶段 B · B2）
> 完成日期：2026-06-30
> 范围：ANI Core / Harbor 镜像推拉闭环 live gate（artifacts + scan-result）

## 目标

在 B1 基础 registry gate 之上，证明 Harbor 中**真实 artifact** 可被 Core API 观测：`GET .../artifacts` 至少 1 条记录 + `GET /registry/images/scan-result` 返回 Harbor provider 结果。

## 实现

- `validate_registry_harbor_live_gate.py` 新增 `--artifact-track`：强制 `--repository` + `--scan-image`，`artifacts_count >= 1`；`production_shape.proof_items` 扩展两项。
- `registry_harbor_runner_common.py`：`push_artifact_test_image`（docker 推送 `pause:3.10`）。
- `run_registry_harbor_live_gate.py --track artifact`：push + artifact-track live gate 一键 runner。
- `scripts/validate_gateway_metadata_p6_b2.py` + test；`make validate-gateway-metadata-p6-b2`。
- `sprint13-production-shaped-gateway-profile.yaml` S08 proof_items 增加 artifacts/scan-result。

## Live gate（人工执行）

```bash
cd repo
export GATEWAY_URL="http://$(hostname -I | awk '{print $1}'):8080/api/v1"   # 或 in-cluster :30080
export HARBOR_URL='https://docker.kubercon.local'
export HARBOR_USERNAME=admin
export HARBOR_PASSWORD='<lab-secret>'
export TENANT_ID='00000000-0000-0000-0000-000000000001'
export HARBOR_TLS_INSECURE=true
export CLEANUP=true

python3 scripts/run_registry_harbor_live_gate.py --track artifact
```

Evidence：`development-records/live-evidence/sprint13-registry-harbor-b2-live-evidence.json`

`SKIP_DOCKER_PUSH=true` 可在镜像已存在时跳过 push。

## 契约验收

```bash
cd repo
make validate-gateway-metadata-p6-b2
make validate-gateway-metadata-p6-b1   # S08 proof_items 已同步扩展
```

## 边界

- 依赖本机 `docker` 推送测试镜像；未覆盖 K8s pull secret 注入（B3）。
- scan-result 依赖 Harbor/Trivy 对 artifact 的扫描状态（无扫描时 status 仍可为 API 可观测值）。
- 不标 full platform production ready。
