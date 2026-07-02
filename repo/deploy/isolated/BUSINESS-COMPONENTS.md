# ANI Isolated 部署配置（业务组件）

本文件描述业务组件（Core 业务服务）部署配置，按组件拆分，并与基础组件解耦说明。

## 1. 范围

业务组件包含：

- `ani-gateway`
- `ani-auth-service`
- `model-service`
- `task-service`
- `reconcile-worker`

## 2. 镜像构建与推送

统一脚本会构建并推送以上 5 个组件镜像：

```bash
cd repo
./scripts/build_push_core_images.sh dev
```

对应镜像名：

- `docker.changqingyun.cn/ani/ani-gateway:dev`
- `docker.changqingyun.cn/ani/ani-auth-service:dev`
- `docker.changqingyun.cn/ani/model-service:dev`
- `docker.changqingyun.cn/ani/task-service:dev`
- `docker.changqingyun.cn/ani/reconcile-worker:dev`

## 3. 当前 Isolated 部署入口现状

## 3.1 已有 Isolated 清单直接覆盖

- `model-service`
- `task-service`
- `reconcile-worker`

入口：

- 清单：`deploy/isolated/services-stack.yaml`
- 脚本：`scripts/deploy_isolated_core_stack.sh`

## 3.2 gateway/auth 当前部署边界

当前 `deploy/isolated` 目录下**没有**独立的 `ani-gateway`/`ani-auth-service` manifest。

因此在 Isolated 路径中：

- 已支持：gateway/auth 镜像构建与推送（`build_push_core_images.sh`）
- 未内置：gateway/auth 的 isolated k8s 清单直接 apply 入口

如果需要把 gateway/auth 也纳入 isolated “一键部署”，建议后续补充：

- `deploy/isolated/gateway-auth.yaml`
- 或在 `deploy/isolated/services-stack.yaml` 中扩展 gateway/auth 资源

## 4. model/task/reconcile 组件配置

## 4.1 统一运行时 Secret

`deploy_isolated_core_stack.sh` 会创建 `ani-services-runtime`（默认 namespace `ani-system`），包含：

- `database_url`
- `nats_url`
- `redis_url`

三个业务服务都通过 `secretKeyRef` 读取该 Secret。

## 4.2 model-service

- 工作负载：`Deployment/model-service`
- 服务：`Service/model-service`
- 端口：`9103`（grpc）、`9203`（health）

```bash
kubectl -n ani-system get deploy model-service
kubectl -n ani-system get svc model-service
kubectl -n ani-system rollout status deploy/model-service --timeout=180s
```

## 4.3 task-service

- 工作负载：`Deployment/task-service`
- 服务：`Service/task-service`
- 端口：`9104`（grpc）、`9204`（health）
- outbox 参数：
  - `OUTBOX_ENABLED=true`
  - `OUTBOX_POLL_INTERVAL_MS=500`
  - `OUTBOX_BATCH_SIZE=100`

```bash
kubectl -n ani-system get deploy task-service
kubectl -n ani-system get svc task-service
kubectl -n ani-system rollout status deploy/task-service --timeout=180s
```

## 4.4 reconcile-worker

- 工作负载：`Deployment/reconcile-worker`
- 服务：`Service/reconcile-worker`
- 端口：`9205`（health）
- ServiceAccount：`ani-gateway`

```bash
kubectl -n ani-system get deploy reconcile-worker
kubectl -n ani-system get svc reconcile-worker
kubectl -n ani-system rollout status deploy/reconcile-worker --timeout=180s
```

## 5. 业务组件部署示例

先确保基础组件已就绪（见 `deploy/isolated/BASE-INFRA-COMPONENTS.md`），再执行：

```bash
cd repo
POSTGRES_PASSWORD=ani_dev_password \
REDIS_PASSWORD=ani_dev_password \
NATS_URL=nats://nats.ani-data.svc.cluster.local:4222 \
./scripts/deploy_isolated_core_stack.sh dev
```

## 6. 一键入口（当前能力）

`scripts/deploy_isolated_all.sh` 当前流程：

1. 构建并推送 core 镜像（包含 gateway/auth）
2. 部署 isolated 基础组件
3. 部署 `model/task/reconcile`
4. 输出健康检查摘要

> 说明：该一键入口当前仍未在 isolated 清单中直接 apply gateway/auth 资源；如需“业务组件五件套都由 isolated 清单部署”，需要新增 gateway/auth 的 isolated manifest。

