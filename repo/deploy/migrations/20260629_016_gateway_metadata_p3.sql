-- ANI Platform · Migration 016
-- Description: Gateway metadata persistence P3 — storage buckets, volume snapshots, filesystem mount targets
-- Depends on: 20260629_015_gateway_metadata_p1.sql
-- Dev bundle: deploy/postgres/gateway-metadata-schema.sql

BEGIN;

CREATE TABLE IF NOT EXISTS storage_buckets (
    tenant_id         UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    bucket_id         TEXT NOT NULL,
    name              TEXT NOT NULL,
    region            TEXT,
    access_mode       TEXT NOT NULL DEFAULT 'private'
        CHECK (access_mode IN ('private', 'public_read')),
    idempotency_key   TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, bucket_id),
    UNIQUE (tenant_id, name)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_storage_buckets_idempotency
    ON storage_buckets (tenant_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL AND idempotency_key <> '';

CREATE INDEX IF NOT EXISTS idx_storage_buckets_tenant_created
    ON storage_buckets (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS volume_snapshots (
    tenant_id         UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    snapshot_id       TEXT NOT NULL,
    volume_id         TEXT NOT NULL,
    name              TEXT NOT NULL,
    description       TEXT,
    status            TEXT NOT NULL DEFAULT 'available'
        CHECK (status IN ('creating', 'available', 'error', 'deleting')),
    size_bytes        BIGINT NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
    idempotency_key   TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, snapshot_id),
    FOREIGN KEY (tenant_id, volume_id) REFERENCES storage_volumes(tenant_id, volume_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_volume_snapshots_idempotency
    ON volume_snapshots (tenant_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL AND idempotency_key <> '';

CREATE INDEX IF NOT EXISTS idx_volume_snapshots_tenant_volume
    ON volume_snapshots (tenant_id, volume_id, created_at DESC);

CREATE TABLE IF NOT EXISTS filesystem_mount_targets (
    tenant_id         UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    mount_target_id   TEXT NOT NULL,
    filesystem_id     TEXT NOT NULL,
    subnet_id         TEXT NOT NULL,
    ip_address        TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'available'
        CHECK (status IN ('creating', 'available', 'deleting', 'error')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, mount_target_id),
    UNIQUE (tenant_id, filesystem_id),
    FOREIGN KEY (tenant_id, filesystem_id) REFERENCES storage_filesystems(tenant_id, filesystem_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_filesystem_mount_targets_tenant_fs
    ON filesystem_mount_targets (tenant_id, filesystem_id);

ALTER TABLE storage_buckets ENABLE ROW LEVEL SECURITY;
ALTER TABLE storage_buckets FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON storage_buckets;
CREATE POLICY tenant_isolation ON storage_buckets
    AS RESTRICTIVE
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

ALTER TABLE volume_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE volume_snapshots FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON volume_snapshots;
CREATE POLICY tenant_isolation ON volume_snapshots
    AS RESTRICTIVE
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

ALTER TABLE filesystem_mount_targets ENABLE ROW LEVEL SECURITY;
ALTER TABLE filesystem_mount_targets FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON filesystem_mount_targets;
CREATE POLICY tenant_isolation ON filesystem_mount_targets
    AS RESTRICTIVE
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

COMMIT;
