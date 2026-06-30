-- ANI Platform · Migration 019
-- Description: Gateway metadata persistence P6-A2 — Secret metadata and bindings (no plaintext)
-- Depends on: 20260629_018_gateway_metadata_p6_a1.sql
-- Dev bundle: deploy/postgres/gateway-metadata-schema.sql

BEGIN;

CREATE TABLE IF NOT EXISTS secrets (
    tenant_id         UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    secret_id         TEXT NOT NULL,
    name              TEXT NOT NULL,
    type              TEXT NOT NULL DEFAULT 'opaque'
        CHECK (type IN ('opaque', 'dockerconfigjson', 'tls')),
    keys              JSONB NOT NULL DEFAULT '[]'::jsonb,
    state             TEXT NOT NULL DEFAULT 'active'
        CHECK (state IN ('active', 'deleted')),
    provider          TEXT NOT NULL DEFAULT 'local',
    real_provider     BOOLEAN NOT NULL DEFAULT FALSE,
    provider_refs     JSONB NOT NULL DEFAULT '[]'::jsonb,
    idempotency_key   TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, secret_id),
    UNIQUE (tenant_id, name)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_secrets_idempotency
    ON secrets (tenant_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL AND idempotency_key <> '';

CREATE INDEX IF NOT EXISTS idx_secrets_tenant_created
    ON secrets (tenant_id, created_at ASC)
    WHERE state <> 'deleted';

CREATE TABLE IF NOT EXISTS secret_bindings (
    tenant_id         UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    binding_id        TEXT NOT NULL,
    secret_id         TEXT NOT NULL,
    target_type       TEXT NOT NULL,
    target_id         TEXT NOT NULL,
    mount_path        TEXT,
    env_prefix        TEXT,
    state             TEXT NOT NULL DEFAULT 'bound'
        CHECK (state IN ('bound', 'released')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, binding_id),
    FOREIGN KEY (tenant_id, secret_id) REFERENCES secrets(tenant_id, secret_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_secret_bindings_tenant_secret
    ON secret_bindings (tenant_id, secret_id, created_at ASC);

ALTER TABLE secrets ENABLE ROW LEVEL SECURITY;
ALTER TABLE secrets FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON secrets;
CREATE POLICY tenant_isolation ON secrets
    AS RESTRICTIVE
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

ALTER TABLE secret_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE secret_bindings FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON secret_bindings;
CREATE POLICY tenant_isolation ON secret_bindings
    AS RESTRICTIVE
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

COMMIT;
