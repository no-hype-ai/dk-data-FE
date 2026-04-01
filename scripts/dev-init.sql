-- dk-data-fe: Local dev database initialisation
-- Runs automatically via docker-entrypoint-initdb.d on first postgres start.
--
-- Creates:
--   • All domain-prefixed schemas (mol_*, hcs_*, ind_*, hcp_*)
--   • Legacy schemas (raw, staging, mart, scoring, meta, api, xenon, application)
--   • PostgREST roles (web_anon, authenticator, analyst, api_user)
--   • meta.data_sources and meta.refresh_log (required by ingestion layer)
--
-- Dev note: authenticator password is hard-coded to 'postgrest_pass' to match
-- the POSTGREST_PASSWORD in .env. Do NOT use this init script in production.

-- =============================================================================
-- EXTENSIONS
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- fuzzy text search (alias bridge)
CREATE EXTENSION IF NOT EXISTS "vector";    -- pgvector (migration 020; future ML embeddings)

-- =============================================================================
-- SCHEMAS
-- =============================================================================

-- Molecule / drug domain
CREATE SCHEMA IF NOT EXISTS mol_raw;
CREATE SCHEMA IF NOT EXISTS mol_bronze;
CREATE SCHEMA IF NOT EXISTS mol_silver;
CREATE SCHEMA IF NOT EXISTS mol_gold;

-- Healthcare system / CMS / provider domain
CREATE SCHEMA IF NOT EXISTS hcs_raw;
CREATE SCHEMA IF NOT EXISTS hcs_bronze;
CREATE SCHEMA IF NOT EXISTS hcs_silver;
CREATE SCHEMA IF NOT EXISTS hcs_gold;

-- Indication / disease domain
CREATE SCHEMA IF NOT EXISTS ind_silver;
CREATE SCHEMA IF NOT EXISTS ind_gold;

-- HCP / KOL / researcher domain
CREATE SCHEMA IF NOT EXISTS hcp_silver;
CREATE SCHEMA IF NOT EXISTS hcp_gold;

-- Infrastructure / API schemas
CREATE SCHEMA IF NOT EXISTS meta;
CREATE SCHEMA IF NOT EXISTS api;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS scoring;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS xenon;
CREATE SCHEMA IF NOT EXISTS application;

-- Legacy bare schemas (kept for backwards compatibility with older migrations)
CREATE SCHEMA IF NOT EXISTS raw;

-- =============================================================================
-- ROLES
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'web_anon') THEN
        CREATE ROLE web_anon NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
        CREATE ROLE analyst NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'api_user') THEN
        CREATE ROLE api_user NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticator') THEN
        -- Dev password matches POSTGREST_PASSWORD in .env / docker-compose.yml
        CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD 'postgrest_pass';
    ELSE
        ALTER ROLE authenticator PASSWORD 'postgrest_pass';
    END IF;
END
$$;

GRANT web_anon  TO authenticator;
GRANT analyst   TO authenticator;
GRANT api_user  TO authenticator;

-- =============================================================================
-- SCHEMA GRANTS
-- =============================================================================

-- web_anon: read-only on api schema
GRANT USAGE ON SCHEMA api TO web_anon;
GRANT SELECT ON ALL TABLES IN SCHEMA api TO web_anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA api GRANT SELECT ON TABLES TO web_anon;

-- analyst: api + scoring + mart + meta read
GRANT USAGE ON SCHEMA api, scoring, mart, meta TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA api     TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA scoring TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA mart    TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA meta    TO analyst;

-- api_user: broad read across all silver/gold schemas
GRANT USAGE ON SCHEMA
    mol_silver, mol_gold,
    hcs_silver, hcs_gold,
    ind_silver, ind_gold,
    hcp_silver, hcp_gold,
    api, mart, scoring, meta, xenon
TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA mol_silver TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA mol_gold   TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA hcs_silver TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA hcs_gold   TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA api        TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA meta       TO api_user;

-- =============================================================================
-- META SCHEMA — core tables required by the ingestion layer
-- =============================================================================

CREATE TABLE IF NOT EXISTS meta.data_sources (
    source_id            SERIAL PRIMARY KEY,
    source_name          TEXT NOT NULL UNIQUE,
    source_type          TEXT,
    source_url           TEXT,
    description          TEXT,
    refresh_frequency    TEXT,
    last_successful_refresh TIMESTAMPTZ,
    last_refresh_attempt    TIMESTAMPTZ,
    last_refresh_status     TEXT,
    record_count            BIGINT,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    topic_tags              TEXT[]  DEFAULT '{}',
    column_descriptions     JSONB   DEFAULT '{}',
    staleness_threshold_hours INTEGER DEFAULT 24,
    table_size_bytes        BIGINT,
    ai_description          TEXT,
    target_tables           TEXT[]  DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS meta.refresh_log (
    log_id               SERIAL PRIMARY KEY,
    source_id            INTEGER NOT NULL REFERENCES meta.data_sources(source_id),
    source_name          TEXT,           -- denormalised for fast alert queries
    refresh_started_at   TIMESTAMPTZ,
    refresh_completed_at TIMESTAMPTZ,
    status               TEXT NOT NULL,
    records_fetched      INTEGER,
    records_inserted     INTEGER,
    records_updated      INTEGER,
    error_message        TEXT,
    _logged_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_refresh_log_source_status
    ON meta.refresh_log (source_id, status, refresh_started_at DESC);
CREATE INDEX IF NOT EXISTS idx_refresh_log_source_name
    ON meta.refresh_log (source_name, refresh_started_at DESC);

-- =============================================================================
-- API SCHEMA — minimal health view (PostgREST requirement)
-- =============================================================================

CREATE OR REPLACE VIEW api.health AS
SELECT
    'ok'::TEXT            AS status,
    NOW()                 AS timestamp,
    current_database()    AS database,
    current_schema()      AS schema;

-- =============================================================================
-- DONE
-- =============================================================================

DO $$
BEGIN
    RAISE NOTICE '=== dk-data-fe dev database ready ===';
    RAISE NOTICE 'Domain schemas: mol_raw/bronze/silver/gold, hcs_raw/bronze/silver/gold';
    RAISE NOTICE 'Infra schemas: meta, api, mart, scoring, staging, xenon, application';
    RAISE NOTICE 'Roles: web_anon, analyst, api_user, authenticator (password: postgrest_pass)';
    RAISE NOTICE 'Run migrations manually: psql -f src/dk_data/sql/migrations/NNN_*.sql';
END
$$;
