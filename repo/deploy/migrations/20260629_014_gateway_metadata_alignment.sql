-- ANI Platform · Migration 014
-- Description: Gateway metadata persistence alignment with Core OpenAPI v1 local profile
-- Depends on: 20260620_013_k8s_cluster_proxy_target_mtls.sql
-- Dev bundle: deploy/postgres/gateway-metadata-schema.sql (includes this file's changes)

BEGIN;

CREATE INDEX IF NOT EXISTS idx_workload_instances_reconcile
    ON workload_instances (state, updated_at);

COMMENT ON INDEX idx_workload_instances_reconcile IS
    'Reconcile worker scan index for non-terminal workload_instances.';

DROP POLICY IF EXISTS tenant_isolation ON network_routes;
CREATE POLICY tenant_isolation ON network_routes
    AS RESTRICTIVE
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

COMMIT;
