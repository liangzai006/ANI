# GATEWAY-METADATA-PERSISTENCE-P6-B1

> 记录类型：Feature batch / Gateway metadata persistence（阶段 B · B1）
> 完成日期：2026-06-30
> 范围：ANI Core / in-cluster production-shaped Gateway + Harbor live gate 契约

## 目标

不依赖本机 `:8080` dev Gateway，通过集群 NodePort（默认 `30080`）与 `ANI_AUTH_MODE=auth_service` 的 production-shaped Gateway 跑 Harbor registry production-shaped live gate；Harbor 凭据经 `ani-registry-production-shaped-runtime` Secret 注入。

## 实现

- 强化 `validate_registry_harbor_live_gate.py`：`--production-shaped` 要求 `--ani-bearer-token`（in-cluster auth）。
- 新增 `run_registry_harbor_live_gate.py --track in-cluster`（NodePort + bearer token + 独立 evidence 路径）。
- 新增 `scripts/validate_gateway_metadata_p6_b1.py` + test；`make validate-gateway-metadata-p6-b1`。
- `sprint13-production-shaped-gateway-profile.yaml` 增加 `slice_proof_items.S08`。
- `validate_sprint13_b_track_production_shape.py` 校验 Deployment `REGISTRY_*` 环境变量来自 `ani-registry-production-shaped-runtime` Secret。
- 既有 `deploy/real-k8s-lab/sprint13-registry-harbor-live.yaml` 作为 Harbor Secret 模板。

## Live gate（人工执行）

```bash
cd repo
# 1. 填写 Harbor 密码后应用 Secret
kubectl apply -f deploy/real-k8s-lab/sprint13-registry-harbor-live.yaml

# 2. 确保 production-shaped Gateway Deployment 已运行（ani-system / NodePort 30080）

# 3. 获取 OIDC bearer token（与 TENANT_ID 一致）
export ANI_BEARER_TOKEN='<token>'
export HARBOR_PASSWORD='<lab-secret>'
export TENANT_ID='00000000-0000-0000-0000-000000000001'
export CLEANUP=true

python3 scripts/run_registry_harbor_live_gate.py --track in-cluster
```

Evidence 输出：`development-records/live-evidence/sprint13-registry-harbor-in-cluster-live-evidence.json`

## 契约验收

```bash
cd repo
make validate-gateway-metadata-p6-b1
make validate-sprint13-b-track-production-shape
```

## 边界

- 本批次交付 **契约 + runner + deployment guard**；in-cluster live evidence 需在有 Gateway/Auth/Harbor 的环境人工执行。
- 本机 `:8080` + `ANI_AUTH_MODE=dev` 路径：`run_registry_harbor_live_gate.py --track production`。
- 不标 full platform production ready。
