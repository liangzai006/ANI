#!/usr/bin/env bash
# One-command isolated deployment for a fresh environment.
# No dependency on deploy/real-k8s-lab.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:-dev}"

POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-ani_dev_password}"
REDIS_PASSWORD="${REDIS_PASSWORD:-ani_dev_password}"
MINIO_ACCESS_KEY_ID="${MINIO_ACCESS_KEY_ID:-ani-minio-access}"
MINIO_SECRET_ACCESS_KEY="${MINIO_SECRET_ACCESS_KEY:-ani-minio-secret}"
MILVUS_MINIO_ACCESS_KEY="${MILVUS_MINIO_ACCESS_KEY:-ani-milvus-access}"
MILVUS_MINIO_SECRET_KEY="${MILVUS_MINIO_SECRET_KEY:-ani-milvus-secret}"

cd "$ROOT"

echo "==> Build and push core images (${VERSION})"
./scripts/build_push_core_images.sh "${VERSION}"

echo "==> Deploy isolated core dependencies"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
REDIS_PASSWORD="${REDIS_PASSWORD}" \
MINIO_ACCESS_KEY_ID="${MINIO_ACCESS_KEY_ID}" \
MINIO_SECRET_ACCESS_KEY="${MINIO_SECRET_ACCESS_KEY}" \
MILVUS_MINIO_ACCESS_KEY="${MILVUS_MINIO_ACCESS_KEY}" \
MILVUS_MINIO_SECRET_KEY="${MILVUS_MINIO_SECRET_KEY}" \
./scripts/deploy_isolated_core_deps.sh

echo "==> Deploy isolated services stack"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
REDIS_PASSWORD="${REDIS_PASSWORD}" \
./scripts/deploy_isolated_core_stack.sh "${VERSION}"

echo "==> Health summary"
for ns in ani-system ani-data ani-s05-objectstore ani-s06-vectorstore ani-s07-observability; do
  echo "# ${ns}"
  kubectl -n "${ns}" get pods
done

NODE_IP="$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')"
echo "==> Probes via ${NODE_IP}"
curl -sf "http://${NODE_IP}:30080/readyz" && echo
curl -sf "http://${NODE_IP}:30900/minio/health/ready" && echo
curl -sf "http://${NODE_IP}:31990/-/ready" && echo

echo "isolated full deployment done"
