# Isolated Deploy (no real-k8s-lab)

本目录用于新环境独立部署，不依赖 `deploy/real-k8s-lab`。

## 组件化配置文档

- 总览（全组件视角）：`deploy/isolated/COMPONENT-DEPLOY-CONFIG.md`
- 基础组件（数据/消息/中间件）：`deploy/isolated/BASE-INFRA-COMPONENTS.md`
- 业务组件（gateway/auth/model/task/reconcile）：`deploy/isolated/BUSINESS-COMPONENTS.md`

## 覆盖范围

- 新增/补齐 services 下的其余组件：
  - `model-service`
  - `task-service`
  - `reconcile-worker`
- 可独立部署 core 依赖：
  - `ani-postgres`
  - `ani-redis`
  - `nats`
  - `ani-s05-minio`
  - `sprint13-milvus`（含 etcd/minio）
  - `sprint13-prometheus`

## 1) 构建并推送镜像

```bash
cd repo
make image-model-service image-task-service image-reconcile-worker VERSION=dev REGISTRY=docker.changqingyun.cn/ani

docker push docker.changqingyun.cn/ani/model-service:dev
docker push docker.changqingyun.cn/ani/task-service:dev
docker push docker.changqingyun.cn/ani/reconcile-worker:dev
```

或统一脚本（已包含 gateway/auth + 这三个服务）：

```bash
./scripts/build_push_core_images.sh dev
```

## 2) 先部署 core 依赖（新环境必做）

```bash
export POSTGRES_PASSWORD='ani_dev_password'
export REDIS_PASSWORD='ani_dev_password'
export MINIO_ACCESS_KEY_ID='ani-minio-access'
export MINIO_SECRET_ACCESS_KEY='ani-minio-secret'
export MILVUS_MINIO_ACCESS_KEY='ani-milvus-access'
export MILVUS_MINIO_SECRET_KEY='ani-milvus-secret'

./scripts/deploy_isolated_core_deps.sh
```

依赖清单文件：`deploy/isolated/core-deps.yaml`

## 3) 部署其余 services 组件

```bash
# 可按需覆盖密码与 NATS 地址
export POSTGRES_PASSWORD='ani_dev_password'
export REDIS_PASSWORD='ani_dev_password'
export NATS_URL='nats://nats.ani-data.svc.cluster.local:4222'

./scripts/deploy_isolated_core_stack.sh dev
```

## 4) 验证

```bash
kubectl -n ani-system get pods | rg 'model-service|task-service|reconcile-worker'
kubectl -n ani-system get svc | rg 'model-service|task-service|reconcile-worker'
kubectl -n ani-data get pods
kubectl -n ani-s05-objectstore get pods
kubectl -n ani-s06-vectorstore get pods
kubectl -n ani-s07-observability get pods
```

## 文件说明

- `deploy/isolated/core-deps.yaml`：独立 core 依赖清单
- `deploy/isolated/services-stack.yaml`：三个服务的 Deployment/Service
- `scripts/deploy_isolated_core_deps.sh`：创建依赖 secret + 部署 core 依赖
- `scripts/deploy_isolated_core_stack.sh`：创建 runtime secret + 部署/滚动验证
- `scripts/deploy_isolated_all.sh`：一键执行“构建推送 + core 依赖 + services 部署 + 健康检查”

## 一键模式

```bash
cd repo
POSTGRES_PASSWORD=ani_dev_password \
REDIS_PASSWORD=ani_dev_password \
MINIO_ACCESS_KEY_ID=ani-minio-access \
MINIO_SECRET_ACCESS_KEY=ani-minio-secret \
MILVUS_MINIO_ACCESS_KEY=ani-milvus-access \
MILVUS_MINIO_SECRET_KEY=ani-milvus-secret \
./scripts/deploy_isolated_all.sh dev
```

