-- ANI Platform · Migration 015
-- Description: Gateway metadata persistence P1 — vector store metadata and token usage idempotency
-- Depends on: 20260629_014_gateway_metadata_alignment.sql
-- Dev bundle: deploy/postgres/gateway-metadata-schema.sql

BEGIN;

CREATE TABLE IF NOT EXISTS metering_records (
    id              BIGSERIAL,
    tenant_id       UUID NOT NULL,
    az_name         TEXT NOT NULL,
    resource_type   TEXT NOT NULL,
    resource_id     UUID,
    quantity        NUMERIC(20, 6) NOT NULL,
    unit            TEXT NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, recorded_at)
);

CREATE INDEX IF NOT EXISTS idx_metering_tenant_time ON metering_records(tenant_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_metering_type ON metering_records(tenant_id, resource_type, recorded_at DESC);

ALTER TABLE metering_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE metering_records FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON metering_records;
CREATE POLICY tenant_isolation ON metering_records
    AS RESTRICTIVE
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

CREATE TABLE IF NOT EXISTS vector_stores (
    tenant_id         UUID NOT NULL,
    store_id          TEXT NOT NULL,
    name              TEXT NOT NULL,
    dimension         INT NOT NULL CHECK (dimension > 0),
    metric            TEXT NOT NULL DEFAULT 'cosine'
        CHECK (metric IN ('cosine', 'l2', 'ip')),
    state             TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'ready', 'failed', 'deleting', 'deleted')),
    reason            TEXT,
    idempotency_key   TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, store_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_vector_stores_idempotency
    ON vector_stores (tenant_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL AND idempotency_key <> '';

CREATE INDEX IF NOT EXISTS idx_vector_stores_tenant_updated
    ON vector_stores (tenant_id, updated_at DESC)
    WHERE state <> 'deleted';

ALTER TABLE vector_stores ENABLE ROW LEVEL SECURITY;
ALTER TABLE vector_stores FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON vector_stores;
CREATE POLICY tenant_isolation ON vector_stores
    AS RESTRICTIVE
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

CREATE TABLE IF NOT EXISTS metering_token_reports (
    id              TEXT PRIMARY KEY,
    tenant_id       UUID NOT NULL,
    idempotency_key TEXT NOT NULL,
    source          TEXT NOT NULL,
    model           TEXT NOT NULL,
    input_tokens    BIGINT NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens   BIGINT NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    request_id      TEXT,
    instance_id     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_metering_token_reports_tenant_created
    ON metering_token_reports (tenant_id, created_at DESC);

ALTER TABLE metering_token_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE metering_token_reports FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON metering_token_reports;
CREATE POLICY tenant_isolation ON metering_token_reports
    AS RESTRICTIVE
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

COMMIT;
