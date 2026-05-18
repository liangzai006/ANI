# M2.2-AUTH-FINAL — Auth 生产收尾

完成日期：2026-05-18
对应 Sprint：Sprint 1
验证结果：`make test` EXIT:0；`make validate-auth-dex-smoke` EXIT:0；`make build`、`make validate-architecture`、`git diff --check` 均通过

## 实现了什么

Auth Service 的 OIDC/JWKS/JWT/API Key 生产护栏已补齐，Gateway Auth REST 表面已接入 auth-service 且无 Services 依赖的 501 stub。Docker Dex auth-code smoke 已在 Mac M1 Docker Desktop 环境通过，M2.2 不再阻塞下一阶段开发。

## 关键文件改动

- `services/auth-service/internal/service/oidc.go` — OIDC nonce/state/redirect_uri/JWKS/time claims 等护栏
- `services/auth-service/internal/service/api_keys.go` — API Key scope、rate limit、创建参数护栏
- `services/ani-gateway/internal/router/auth.go` — Auth REST 路由接入 auth-service
- `services/ani-gateway/internal/middleware/auth_client.go` — Gateway auth-service gRPC client 方法补齐
- `api/openapi/v1.yaml` — Auth REST API 契约同步
- `scripts/validate_auth_gateway_contract.py` — 本地 Auth Gateway/API 合同守卫
- `scripts/smoke_auth_dex.py` — Docker Dex auth-code smoke 验收脚本
- `deploy/docker/config/dex-dev.yaml` — Dex 开发 profile 配置
- `deploy/docker/README.md` — Dex smoke 验收说明

## 完工标准达成

- [x] Auth Service OIDC/JWKS/JWT/API Key 自动化测试通过
- [x] Gateway Auth REST 表面无 501 stub
- [x] API 契约、Gateway route、Auth public/protected 边界由 `make validate-auth-contract` 守卫
- [x] Docker Dex discovery、JWKS、登录、authorization code callback 和 token endpoint smoke 通过
- [x] `make build` 全服务构建通过
- [x] `make test` 全通
- [x] `make validate-architecture` 通过
- [x] `git diff --check` 通过
