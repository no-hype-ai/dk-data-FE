-- Migration 067: API audit log table
-- Feature: 013-observability-governance (US3: Audit Trail)
-- Tasks: T011
-- Purpose: Create append-only audit log table for API request tracking
-- Run: psql -h localhost -p 5433 -U postgres -d dk_data -f migrations/067_audit_log_table.sql

BEGIN;

-- =============================================================================
-- meta.ops_api_audit_log — Append-only audit trail for API requests
-- =============================================================================

CREATE TABLE IF NOT EXISTS meta.ops_api_audit_log (
    id              BIGSERIAL       PRIMARY KEY,
    request_id      UUID            NOT NULL,
    timestamp       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    source          VARCHAR(20)     NOT NULL DEFAULT 'job-trigger',
    method          VARCHAR(10),
    path            TEXT,
    query_params    JSONB,
    user_role       VARCHAR(50),
    user_sub        VARCHAR(255),
    ip_address      INET,
    user_agent      TEXT,
    status_code     SMALLINT,
    response_time_ms INTEGER,
    action          VARCHAR(50),
    category        VARCHAR(20),
    details         JSONB,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- Indexes for common query patterns
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_api_audit_timestamp  ON meta.ops_api_audit_log (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_api_audit_user_role  ON meta.ops_api_audit_log (user_role);
CREATE INDEX IF NOT EXISTS idx_api_audit_path       ON meta.ops_api_audit_log (path);
CREATE INDEX IF NOT EXISTS idx_api_audit_category   ON meta.ops_api_audit_log (category);

-- -----------------------------------------------------------------------------
-- Append-only enforcement: revoke UPDATE and DELETE from all roles
-- -----------------------------------------------------------------------------
REVOKE UPDATE, DELETE ON meta.ops_api_audit_log FROM PUBLIC;

DO $revoke$
BEGIN
    -- Revoke destructive operations from all known roles
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'web_anon') THEN
        EXECUTE 'REVOKE UPDATE, DELETE ON meta.ops_api_audit_log FROM web_anon';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analyst') THEN
        EXECUTE 'REVOKE UPDATE, DELETE ON meta.ops_api_audit_log FROM analyst';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_user') THEN
        EXECUTE 'REVOKE UPDATE, DELETE ON meta.ops_api_audit_log FROM api_user';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'readonly') THEN
        EXECUTE 'REVOKE UPDATE, DELETE ON meta.ops_api_audit_log FROM readonly';
    END IF;
END $revoke$;

-- -----------------------------------------------------------------------------
-- Grant INSERT to api_user and analyst (application writes)
-- Grant SELECT to api_user only (read audit data)
-- -----------------------------------------------------------------------------
DO $grants$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_user') THEN
        EXECUTE 'GRANT INSERT, SELECT ON meta.ops_api_audit_log TO api_user';
        EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE meta.ops_api_audit_log_id_seq TO api_user';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analyst') THEN
        EXECUTE 'GRANT INSERT ON meta.ops_api_audit_log TO analyst';
        EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE meta.ops_api_audit_log_id_seq TO analyst';
    END IF;
END $grants$;

-- -----------------------------------------------------------------------------
-- PostgREST audit trigger function
-- Captures JWT claims from current_setting('request.jwt.claims', true)
-- for auditing API view access through PostgREST
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION meta.audit_postgrest_access()
RETURNS TRIGGER AS $func$
DECLARE
    jwt_claims JSONB;
    v_user_role VARCHAR(50);
    v_user_sub  VARCHAR(255);
BEGIN
    -- Extract JWT claims set by PostgREST
    BEGIN
        jwt_claims := current_setting('request.jwt.claims', true)::JSONB;
    EXCEPTION WHEN OTHERS THEN
        jwt_claims := NULL;
    END;

    IF jwt_claims IS NOT NULL THEN
        v_user_role := jwt_claims->>'role';
        v_user_sub  := jwt_claims->>'sub';
    END IF;

    -- Populate audit fields from JWT if not already set by the application
    IF NEW.user_role IS NULL THEN
        NEW.user_role := v_user_role;
    END IF;
    IF NEW.user_sub IS NULL THEN
        NEW.user_sub := v_user_sub;
    END IF;

    -- Ensure timestamp is set
    IF NEW.timestamp IS NULL THEN
        NEW.timestamp := NOW();
    END IF;

    RETURN NEW;
END;
$func$ LANGUAGE plpgsql SECURITY DEFINER;

-- Attach trigger to api_audit_log
DROP TRIGGER IF EXISTS trg_audit_postgrest ON meta.ops_api_audit_log;
CREATE TRIGGER trg_audit_postgrest
    BEFORE INSERT ON meta.ops_api_audit_log
    FOR EACH ROW
    EXECUTE FUNCTION meta.audit_postgrest_access();

COMMIT;

-- =============================================================================
-- COMPLETION MESSAGE
-- =============================================================================
DO $$
BEGIN
    RAISE NOTICE 'Audit log migration complete (067_audit_log_table.sql)';
    RAISE NOTICE 'Table: meta.ops_api_audit_log (append-only)';
    RAISE NOTICE 'Indexes: timestamp, user_role, path, category';
    RAISE NOTICE 'Trigger: trg_audit_postgrest (captures JWT claims)';
    RAISE NOTICE 'Grants: INSERT to api_user+analyst, SELECT to api_user only';
END
$$;
