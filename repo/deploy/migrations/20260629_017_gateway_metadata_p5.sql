-- ANI Platform · Migration 017
-- Description: Gateway metadata persistence P5 — registry projects, repository permissions, pull secret metadata
-- Depends on: 20260629_016_gateway_metadata_p3.sql
-- Dev bundle: deploy/postgres/gateway-metadata-schema.sql

BEGIN;

CREATE TABLE IF NOT EXISTS registry_projects (
    tenant_id         UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    project_id        TEXT NOT NULL,
    name              TEXT NOT NULL,
    public            BOOLEAN NOT NULL DEFAULT FALSE,
    provider_mode     TEXT NOT NULL DEFAULT 'local'
        CHECK (provider_mode IN ('local', 'harbor')),
    idempotency_key   TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, project_id),
    UNIQUE (tenant_id, name)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_registry_projects_idempotency
    ON registry_projects (tenant_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL AND idempotency_key <> '';

CREATE INDEX IF NOT EXISTS idx_registry_projects_tenant_created
    ON registry_projects (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS registry_repository_permissions (
    tenant_id         UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    project           TEXT NOT NULL,
    repository        TEXT NOT NULL,
    subject           TEXT NOT NULL,
    actions           JSONB NOT NULL DEFAULT '[]'::jsonb,
    state             TEXT NOT NULL DEFAULT 'active'
        CHECK (state IN ('active', 'duplicate')),
    idempotency_key   TEXT,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, project, repository, subject)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_registry_repository_permissions_idempotency
    ON registry_repository_permissions (tenant_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL AND idempotency_key <> '';

CREATE INDEX IF NOT EXISTS idx_registry_repository_permissions_tenant_project
    ON registry_repository_permissions (tenant_id, project, repository);

CREATE TABLE IF NOT EXISTS registry_pull_secrets (
    tenant_id         UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    project           TEXT NOT NULL,
    name              TEXT NOT NULL,
    secret_ref        TEXT NOT NULL,
    registry_host     TEXT NOT NULL,
    username          TEXT NOT NULL,
    namespace         TEXT,
    state             TEXT NOT NULL DEFAULT 'active'
        CHECK (state IN ('active', 'duplicate')),
    idempotency_key   TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, project, name)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_registry_pull_secrets_idempotency
    ON registry_pull_secrets (tenant_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL AND idempotency_key <> '';

CREATE INDEX IF NOT EXISTS idx_registry_pull_secrets_tenant_project
    ON registry_pull_secrets (tenant_id, project, created_at DESC);

ALTER TABLE registry_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE registry_projects FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON registry_projects;
CREATE POLICY tenant_isolation ON registry_projects
    AS RESTRICTIVE
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

ALTER TABLE registry_repository_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE registry_repository_permissions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON registry_repository_permissions;
CREATE POLICY tenant_isolation ON registry_repository_permissions
    AS RESTRICTIVE
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

ALTER TABLE registry_pull_secrets ENABLE ROW LEVEL SECURITY;
ALTER TABLE registry_pull_secrets FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON registry_pull_secrets;
CREATE POLICY tenant_isolation ON registry_pull_secrets
    AS RESTRICTIVE
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

COMMIT;
