#!/usr/bin/env bash
# Independent deployment entrypoint (no deploy/real-k8s-lab dependency).
# Deploys extra services (model/task/reconcile) and ensures runtime secret exists.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:-dev}"
NAMESPACE="${NAMESPACE:-ani-system}"

POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-ani_dev_password}"
REDIS_PASSWORD="${REDIS_PASSWORD:-ani_dev_password}"
NATS_URL="${NATS_URL:-nats://nats.ani-data.svc.cluster.local:4222}"

DB_URL="postgres://ani:${POSTGRES_PASSWORD}@ani-postgres.ani-data.svc.cluster.local:5432/ani?sslmode=disable"
REDIS_URL="redis://:${REDIS_PASSWORD}@ani-redis.ani-data.svc.cluster.local:6379/0"

kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

kubectl -n "$NAMESPACE" create secret generic ani-services-runtime \
  --from-literal=database_url="$DB_URL" \
  --from-literal=nats_url="$NATS_URL" \
  --from-literal=redis_url="$REDIS_URL" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f "$ROOT/deploy/isolated/business-stack.yaml"
kubectl -n "$NAMESPACE" set image deploy/ani-gateway ani-gateway=docker.changqingyun.cn/ani/ani-gateway:${VERSION}
kubectl -n "$NAMESPACE" set image deploy/ani-auth-service ani-auth-service=docker.changqingyun.cn/ani/ani-auth-service:${VERSION}
kubectl -n "$NAMESPACE" set image deploy/model-service model-service=docker.changqingyun.cn/ani/model-service:${VERSION}
kubectl -n "$NAMESPACE" set image deploy/task-service task-service=docker.changqingyun.cn/ani/task-service:${VERSION}
kubectl -n "$NAMESPACE" set image deploy/reconcile-worker reconcile-worker=docker.changqingyun.cn/ani/reconcile-worker:${VERSION}

kubectl -n "$NAMESPACE" rollout status deploy/ani-auth-service --timeout=180s
kubectl -n "$NAMESPACE" rollout status deploy/ani-gateway --timeout=180s
kubectl -n "$NAMESPACE" rollout status deploy/model-service --timeout=180s
kubectl -n "$NAMESPACE" rollout status deploy/task-service --timeout=180s
kubectl -n "$NAMESPACE" rollout status deploy/reconcile-worker --timeout=180s

echo "isolated services deployed in ${NAMESPACE}"
kubectl -n "$NAMESPACE" get pods | rg 'ani-gateway|ani-auth-service|model-service|task-service|reconcile-worker'
