-- ANI Platform · Migration 018
-- Description: Gateway metadata persistence P6-A1 — K8s cluster and node pool control-plane metadata
-- Depends on: 20260629_017_gateway_metadata_p5.sql
-- Dev bundle: deploy/postgres/gateway-metadata-schema.sql

BEGIN;

CREATE TABLE IF NOT EXISTS k8s_clusters (
    tenant_id         UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    cluster_id        TEXT NOT NULL,
    name              TEXT NOT NULL,
    version           TEXT NOT NULL DEFAULT '',
    state             TEXT NOT NULL DEFAULT 'provisioning'
        CHECK (state IN ('provisioning', 'running', 'deleting')),
    reason            TEXT,
    provider          TEXT NOT NULL DEFAULT 'local',
    real_provider     BOOLEAN NOT NULL DEFAULT FALSE,
    provider_refs     JSONB NOT NULL DEFAULT '[]'::jsonb,
    idempotency_key   TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, cluster_id),
    UNIQUE (tenant_id, name)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_k8s_clusters_idempotency
    ON k8s_clusters (tenant_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL AND idempotency_key <> '';

CREATE INDEX IF NOT EXISTS idx_k8s_clusters_tenant_created
    ON k8s_clusters (tenant_id, created_at ASC);

CREATE TABLE IF NOT EXISTS k8s_cluster_node_pools (
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    cluster_id          TEXT NOT NULL,
    node_pool_id        TEXT NOT NULL,
    name                TEXT NOT NULL,
    node_count          INT NOT NULL CHECK (node_count >= 0),
    instance_type       TEXT NOT NULL,
    gpu_vendor          TEXT,
    gpu_model           TEXT,
    gpu_count           INT NOT NULL DEFAULT 0,
    gpu_resource_name   TEXT,
    state               TEXT NOT NULL DEFAULT 'running'
        CHECK (state IN ('running', 'deleting')),
    reason              TEXT,
    provider            TEXT NOT NULL DEFAULT 'local',
    real_provider       BOOLEAN NOT NULL DEFAULT FALSE,
    provider_refs       JSONB NOT NULL DEFAULT '[]'::jsonb,
    idempotency_key     TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, node_pool_id),
    UNIQUE (tenant_id, cluster_id, name),
    FOREIGN KEY (tenant_id, cluster_id) REFERENCES k8s_clusters(tenant_id, cluster_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_k8s_cluster_node_pools_idempotency
    ON k8s_cluster_node_pools (tenant_id, cluster_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL AND idempotency_key <> '';

CREATE INDEX IF NOT EXISTS idx_k8s_cluster_node_pools_tenant_cluster
    ON k8s_cluster_node_pools (tenant_id, cluster_id, created_at ASC);

ALTER TABLE k8s_clusters ENABLE ROW LEVEL SECURITY;
ALTER TABLE k8s_clusters FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON k8s_clusters;
CREATE POLICY tenant_isolation ON k8s_clusters
    AS RESTRICTIVE
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

ALTER TABLE k8s_cluster_node_pools ENABLE ROW LEVEL SECURITY;
ALTER TABLE k8s_cluster_node_pools FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON k8s_cluster_node_pools;
CREATE POLICY tenant_isolation ON k8s_cluster_node_pools
    AS RESTRICTIVE
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

COMMIT;
