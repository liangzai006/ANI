# ANI Isolated 部署配置（基础组件）

本文件只描述基础组件（数据、消息、中间件）部署配置，且仅使用 `deploy/isolated` 路径，不依赖 `deploy/real-k8s-lab`。

## 1. 部署入口

- 统一脚本：`scripts/deploy_isolated_core_deps.sh`
- 组件清单：`deploy/isolated/core-deps.yaml`

## 2. 组件清单（基础层）

- `ani-postgres`（PostgreSQL）
- `ani-redis`（Redis）
- `nats`（NATS）
- `ani-s05-minio`（Object Store MinIO）
- `sprint13-milvus`（Milvus，依赖 etcd/minio）
- `sprint13-prometheus`（Prometheus）

## 3. 基础组件统一变量与 Secret

`deploy_isolated_core_deps.sh` 支持以下环境变量（有默认值）：

- `POSTGRES_PASSWORD`（默认 `ani_dev_password`）
- `REDIS_PASSWORD`（默认 `ani_dev_password`）
- `MINIO_ACCESS_KEY_ID`（默认 `ani-minio-access`）
- `MINIO_SECRET_ACCESS_KEY`（默认 `ani-minio-secret`）
- `MILVUS_MINIO_ACCESS_KEY`（默认 `ani-milvus-access`）
- `MILVUS_MINIO_SECRET_KEY`（默认 `ani-milvus-secret`）

脚本会创建：

- `ani-data/ani-postgres-secret`
- `ani-data/ani-redis-secret`
- `ani-s05-objectstore/ani-s05-minio-root`
- `ani-s06-vectorstore/sprint13-milvus-minio`

## 4. 按组件配置与验证

## 4.1 PostgreSQL（ani-postgres）

- 命名空间：`ani-data`
- 工作负载：`StatefulSet/ani-postgres`
- 服务：`Service/ani-postgres`
- Secret：`ani-postgres-secret`

```bash
kubectl -n ani-data get sts ani-postgres
kubectl -n ani-data get svc ani-postgres
kubectl -n ani-data rollout status sts/ani-postgres --timeout=240s
```

## 4.2 Redis（ani-redis）

- 命名空间：`ani-data`
- 工作负载：`Deployment/ani-redis`
- 服务：`Service/ani-redis`
- Secret：`ani-redis-secret`

```bash
kubectl -n ani-data get deploy ani-redis
kubectl -n ani-data get svc ani-redis
kubectl -n ani-data rollout status deploy/ani-redis --timeout=240s
```

## 4.3 NATS（nats）

- 命名空间：`ani-data`
- 工作负载：`Deployment/nats`
- 服务：`Service/nats`

```bash
kubectl -n ani-data get deploy nats
kubectl -n ani-data get svc nats
kubectl -n ani-data rollout status deploy/nats --timeout=240s
```

## 4.4 Object Store（ani-s05-minio）

- 命名空间：`ani-s05-objectstore`
- 工作负载：`Deployment/ani-s05-minio`
- 服务：`Service/ani-s05-minio`
- Secret：`ani-s05-minio-root`

```bash
kubectl -n ani-s05-objectstore get deploy ani-s05-minio
kubectl -n ani-s05-objectstore get svc ani-s05-minio
kubectl -n ani-s05-objectstore rollout status deploy/ani-s05-minio --timeout=240s
```

## 4.5 Vector Store（sprint13-milvus）

- 命名空间：`ani-s06-vectorstore`
- 依赖：`sprint13-milvus-etcd`、`sprint13-milvus-minio`
- 主组件：`sprint13-milvus`
- Secret：`sprint13-milvus-minio`

```bash
kubectl -n ani-s06-vectorstore get deploy sprint13-milvus-etcd sprint13-milvus-minio sprint13-milvus
kubectl -n ani-s06-vectorstore get svc sprint13-milvus-etcd sprint13-milvus-minio sprint13-milvus
kubectl -n ani-s06-vectorstore rollout status deploy/sprint13-milvus --timeout=240s
```

## 4.6 Observability（sprint13-prometheus）

- 命名空间：`ani-s07-observability`
- 工作负载：`Deployment/sprint13-prometheus`
- 服务：`Service/sprint13-prometheus`
- 组件配置：`ConfigMap/sprint13-prometheus-config`

```bash
kubectl -n ani-s07-observability get sa sprint13-prometheus
kubectl -n ani-s07-observability get configmap sprint13-prometheus-config
kubectl -n ani-s07-observability get deploy sprint13-prometheus
kubectl -n ani-s07-observability rollout status deploy/sprint13-prometheus --timeout=240s
```

## 5. 最小部署示例

```bash
cd repo
POSTGRES_PASSWORD=ani_dev_password \
REDIS_PASSWORD=ani_dev_password \
MINIO_ACCESS_KEY_ID=ani-minio-access \
MINIO_SECRET_ACCESS_KEY=ani-minio-secret \
MILVUS_MINIO_ACCESS_KEY=ani-milvus-access \
MILVUS_MINIO_SECRET_KEY=ani-milvus-secret \
./scripts/deploy_isolated_core_deps.sh
```

