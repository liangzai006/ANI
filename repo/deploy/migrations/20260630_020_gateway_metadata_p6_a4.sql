-- ANI Platform · Migration 020
-- Description: Gateway metadata persistence P6-A4 — encryption key metadata (no key material)
-- Depends on: 20260630_019_gateway_metadata_p6_a2.sql
-- Dev bundle: deploy/postgres/gateway-metadata-schema.sql

BEGIN;

CREATE TABLE IF NOT EXISTS encryption_keys (
    tenant_id         UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    key_id            TEXT NOT NULL,
    name              TEXT NOT NULL,
    algorithm         TEXT NOT NULL DEFAULT 'SM4'
        CHECK (algorithm IN ('SM4', 'AES256')),
    state             TEXT NOT NULL DEFAULT 'active'
        CHECK (state IN ('active', 'rotated', 'revoked', 'deleted')),
    provider          TEXT NOT NULL DEFAULT 'local',
    real_provider     BOOLEAN NOT NULL DEFAULT FALSE,
    provider_refs     JSONB NOT NULL DEFAULT '[]'::jsonb,
    idempotency_key   TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, key_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_encryption_keys_idempotency
    ON encryption_keys (tenant_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL AND idempotency_key <> '';

CREATE INDEX IF NOT EXISTS idx_encryption_keys_tenant_created
    ON encryption_keys (tenant_id, created_at ASC);

ALTER TABLE encryption_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE encryption_keys FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON encryption_keys;
CREATE POLICY tenant_isolation ON encryption_keys
    AS RESTRICTIVE
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

COMMIT;
