#!/usr/bin/env bash
# Deploy isolated core dependencies without using deploy/real-k8s-lab.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-ani_dev_password}"
REDIS_PASSWORD="${REDIS_PASSWORD:-ani_dev_password}"
MINIO_ACCESS_KEY_ID="${MINIO_ACCESS_KEY_ID:-ani-minio-access}"
MINIO_SECRET_ACCESS_KEY="${MINIO_SECRET_ACCESS_KEY:-ani-minio-secret}"
MILVUS_MINIO_ACCESS_KEY="${MILVUS_MINIO_ACCESS_KEY:-ani-milvus-access}"
MILVUS_MINIO_SECRET_KEY="${MILVUS_MINIO_SECRET_KEY:-ani-milvus-secret}"

kubectl create namespace ani-data --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace ani-s05-objectstore --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace ani-s06-vectorstore --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace ani-s07-observability --dry-run=client -o yaml | kubectl apply -f -

kubectl -n ani-data create secret generic ani-postgres-secret \
  --from-literal=POSTGRES_USER=ani \
  --from-literal=POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
  --from-literal=POSTGRES_DB=ani \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n ani-data create secret generic ani-redis-secret \
  --from-literal=password="${REDIS_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n ani-s05-objectstore create secret generic ani-s05-minio-root \
  --from-literal=access_key_id="${MINIO_ACCESS_KEY_ID}" \
  --from-literal=secret_access_key="${MINIO_SECRET_ACCESS_KEY}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n ani-s06-vectorstore create secret generic sprint13-milvus-minio \
  --from-literal=access_key="${MILVUS_MINIO_ACCESS_KEY}" \
  --from-literal=secret_key="${MILVUS_MINIO_SECRET_KEY}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f "$ROOT/deploy/isolated/base-infra.yaml"

kubectl -n ani-data rollout status deploy/ani-redis --timeout=240s
kubectl -n ani-data rollout status deploy/nats --timeout=240s
kubectl -n ani-data rollout status sts/ani-postgres --timeout=240s
kubectl -n ani-s05-objectstore rollout status deploy/ani-s05-minio --timeout=240s
kubectl -n ani-s06-vectorstore rollout status deploy/sprint13-milvus --timeout=240s
kubectl -n ani-s07-observability rollout status deploy/sprint13-prometheus --timeout=240s

echo "isolated core dependencies deployed"
