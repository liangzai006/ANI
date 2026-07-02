#!/usr/bin/env bash
# Create Sprint 13 production-shaped runtime secrets in ani-system.
# Credentials are not stored in git; pass via environment variables.
#
# Required:
#   POSTGRES_PASSWORD
#   REDIS_PASSWORD
#   MINIO_ACCESS_KEY_ID
#   MINIO_SECRET_ACCESS_KEY
#   HARBOR_PASSWORD
#
# Optional:
#   OIDC_CLIENT_SECRET (default: ani-dex-client-secret-dev)
#   NATS_URL (default: nats://nats.ani-data.svc.cluster.local:4222)
#   MINIO_ENDPOINT (default: in-cluster MinIO service)
#   MINIO_PUBLIC_ENDPOINT (default: http://<first-node-ip>:30900)
#   MILVUS_ENDPOINT (default: in-cluster Milvus service)
#   HARBOR_ENDPOINT (default: docker.kubercon.local)
#   HARBOR_USERNAME (default: admin)
#   NAMESPACE (default: ani-system)
#
# JWT key pair is generated on each run unless JWT_PRIVATE_KEY_FILE / JWT_PUBLIC_KEY_FILE are set.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="${NAMESPACE:-ani-system}"
WORKDIR="${TMPDIR:-/tmp}/ani-sprint13-secrets-$$"
mkdir -p "$WORKDIR"

require_env() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "missing required env: $name" >&2
    exit 1
  fi
}

require_env POSTGRES_PASSWORD
require_env REDIS_PASSWORD
require_env MINIO_ACCESS_KEY_ID
require_env MINIO_SECRET_ACCESS_KEY
require_env HARBOR_PASSWORD

OIDC_CLIENT_SECRET="${OIDC_CLIENT_SECRET:-ani-dex-client-secret-dev}"
NATS_URL="${NATS_URL:-nats://nats.ani-data.svc.cluster.local:4222}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://ani-s05-minio.ani-s05-objectstore.svc.cluster.local:9000}"
MILVUS_ENDPOINT="${MILVUS_ENDPOINT:-http://sprint13-milvus.ani-s06-vectorstore.svc.cluster.local:19530}"
HARBOR_ENDPOINT="${HARBOR_ENDPOINT:-docker.kubercon.local}"
HARBOR_USERNAME="${HARBOR_USERNAME:-admin}"

if [ -z "${MINIO_PUBLIC_ENDPOINT:-}" ]; then
  NODE_IP="$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || true)"
  MINIO_PUBLIC_ENDPOINT="http://${NODE_IP:-127.0.0.1}:30900"
fi

JWT_PRIVATE_KEY_FILE="${JWT_PRIVATE_KEY_FILE:-$WORKDIR/jwt_private.pem}"
JWT_PUBLIC_KEY_FILE="${JWT_PUBLIC_KEY_FILE:-$WORKDIR/jwt_public.pem}"
if [ ! -f "$JWT_PRIVATE_KEY_FILE" ] || [ ! -f "$JWT_PUBLIC_KEY_FILE" ]; then
  openssl genrsa -out "$JWT_PRIVATE_KEY_FILE" 2048 >/dev/null 2>&1
  openssl rsa -in "$JWT_PRIVATE_KEY_FILE" -pubout -out "$JWT_PUBLIC_KEY_FILE" >/dev/null 2>&1
fi

DB_URL="postgres://ani:${POSTGRES_PASSWORD}@ani-postgres.ani-data.svc.cluster.local:5432/ani?sslmode=disable"
REDIS_URL="redis://:${REDIS_PASSWORD}@ani-redis.ani-data.svc.cluster.local:6379/0"

kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

kubectl -n "$NAMESPACE" create secret generic ani-gateway-production-shaped-runtime \
  --from-literal=database_url="$DB_URL" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n "$NAMESPACE" create secret generic ani-auth-production-shaped-runtime \
  --from-literal=database_url="$DB_URL" \
  --from-literal=redis_url="$REDIS_URL" \
  --from-literal=nats_url="$NATS_URL" \
  --from-literal=oidc_client_secret="$OIDC_CLIENT_SECRET" \
  --from-file=jwt_private_key_pem="$JWT_PRIVATE_KEY_FILE" \
  --from-file=jwt_public_key_pem="$JWT_PUBLIC_KEY_FILE" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n "$NAMESPACE" create secret generic ani-objectstore-production-shaped-runtime \
  --from-literal=endpoint="$MINIO_ENDPOINT" \
  --from-literal=public_endpoint="$MINIO_PUBLIC_ENDPOINT" \
  --from-literal=access_key_id="$MINIO_ACCESS_KEY_ID" \
  --from-literal=secret_access_key="$MINIO_SECRET_ACCESS_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n "$NAMESPACE" create secret generic ani-vectorstore-production-shaped-runtime \
  --from-literal=endpoint="$MILVUS_ENDPOINT" \
  --from-literal=token='' \
  --from-literal=database='default' \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n "$NAMESPACE" create secret generic ani-registry-production-shaped-runtime \
  --from-literal=endpoint="$HARBOR_ENDPOINT" \
  --from-literal=username="$HARBOR_USERNAME" \
  --from-literal=password="$HARBOR_PASSWORD" \
  --from-literal=secure='true' \
  --from-literal=tls_insecure='true' \
  --dry-run=client -o yaml | kubectl apply -f -

echo "✅ Sprint 13 runtime secrets applied in namespace ${NAMESPACE}"
