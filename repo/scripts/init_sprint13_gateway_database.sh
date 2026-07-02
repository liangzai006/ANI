#!/usr/bin/env bash
# Initialize Gateway / Auth metadata schema in the lab Postgres StatefulSet.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="${NAMESPACE:-ani-data}"
POD="${POD:-ani-postgres-0}"
SQL="${SQL:-$ROOT/deploy/postgres/ani-dev-database-init.sql}"

kubectl -n "$NAMESPACE" wait --for=condition=Ready "pod/$POD" --timeout=180s
kubectl -n "$NAMESPACE" exec -i "$POD" -- psql -U ani -d ani -v ON_ERROR_STOP=1 < "$SQL"
echo "✅ database initialized from $(basename "$SQL")"
