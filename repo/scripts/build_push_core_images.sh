#!/usr/bin/env bash
# Build and push ANI Core service images to docker.changqingyun.cn/ani/.
#
# Usage:
#   ./scripts/build_push_core_images.sh [VERSION]
#   VERSION defaults to "dev".
#
# Optional lab mirror (Harbor on docker.kubercon.local):
#   MIRROR_REGISTRY=docker.kubercon.local/common/ani ./scripts/build_push_core_images.sh dev

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:-dev}"
REGISTRY="${REGISTRY:-docker.changqingyun.cn/ani}"
MIRROR_REGISTRY="${MIRROR_REGISTRY:-}"

cd "$ROOT"

make image-gateway image-auth-service image-model-service image-task-service image-reconcile-worker VERSION="$VERSION" REGISTRY="$REGISTRY"

for name in ani-gateway ani-auth-service model-service task-service reconcile-worker; do
  src="${REGISTRY}/${name}:${VERSION}"
  echo "→ push ${src}"
  docker push "${src}"
  if [ -n "$MIRROR_REGISTRY" ]; then
    dst="${MIRROR_REGISTRY}/${name}:${VERSION}"
    docker tag "${src}" "${dst}"
    echo "→ push mirror ${dst}"
    docker push "${dst}"
  fi
done

echo "✅ Core images published:"
echo "   ${REGISTRY}/ani-gateway:${VERSION}"
echo "   ${REGISTRY}/ani-auth-service:${VERSION}"
echo "   ${REGISTRY}/model-service:${VERSION}"
echo "   ${REGISTRY}/task-service:${VERSION}"
echo "   ${REGISTRY}/reconcile-worker:${VERSION}"
