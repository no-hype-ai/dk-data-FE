-- Feature: Horizon 3 / plan §D.2 — declarative source descriptors
--
-- Creates ``meta.source_registry``: the canonical registry of every
-- onboarded data source, materialised in the database so the TS CLI
-- (`dk data source list`), the in-cluster dispatcher (§D.1), the
-- observability dashboards (`dk-data-fe-source-registry` from §J.3),
-- and the admission controller (§D.3) all read from one place.
--
-- The row shape mirrors the per-source YAML descriptor at
-- ``.dk/sources/<name>.yaml``. Descriptors are the source of truth on
-- disk; ``meta.source_registry`` is a projection of those descriptors
-- refreshed via ``python -m dk_data.ingestion.source_registry --sync``.
-- sync is idempotent (ON CONFLICT DO UPDATE).
--
-- Schema notes
-- ------------
--   * ``name`` is the PK (natural key). Descriptor filenames match
--     ``<name>.yaml`` and the name must satisfy ``^[a-z][a-z0-9_]*$``
--     (enforced in Python; CHECK constraint here mirrors it so an
--     accidentally-invalid INSERT from a DBA also fails).
--   * ``domain`` is constrained to the canonical list from CLAUDE.md
--     plus the new ``dev`` domain for medical devices (plan §E.3).
--   * ``tier`` is 1..8 — see ``dk_data.ingestion.load_order`` for the
--     orchestration tier vocabulary. The enum is the accessibility tier
--     (T1..T4) lives elsewhere as a label on the GH issue, not here.
--   * ``depends_on`` / ``fetch`` / ``consumes`` are JSONB so they can
--     evolve without a DDL migration each time a descriptor field is
--     added. JSON schema validation happens in the Python loader.
--     NOTE: ``fetch`` is a SQL-reserved word (FETCH cursor syntax), so
--     the column is double-quoted in DDL and in every query that
--     references it. The descriptor YAML key stays bare ``fetch:``.
--   * ``status`` is a soft enum (TEXT with CHECK) — 'stub' on initial
--     registration, 'fetcher_ready' once the fetcher module exists,
--     'live' once the source has a successful run in ``meta.transform_runs``.
--
-- Idempotency
-- -----------
--   Every statement is IF NOT EXISTS / CREATE OR REPLACE. Re-running the
--   migration is a no-op. The ``updated_at`` default + ``sync_to_db``
--   upserts carry the actual freshness signal for dashboards.
--
-- Migration number rationale
-- --------------------------
--   232 is taken by hydration_backlog.sql (C.3). D.3 will land
--   ``resource_budget`` at a later number. 233 is the next free slot.

BEGIN;

SET LOCAL statement_timeout = '120s';
SET LOCAL lock_timeout = '10s';

CREATE TABLE IF NOT EXISTS meta.source_registry (
  name                   TEXT PRIMARY KEY
                           CHECK (name ~ '^[a-z][a-z0-9_]*$'),
  domain                 TEXT NOT NULL
                           CHECK (domain IN ('mol', 'hcs', 'hcp', 'ind', 'ip', 'dev')),
  tier                   INT  NOT NULL
                           CHECK (tier BETWEEN 1 AND 8),
  depends_on             JSONB NOT NULL DEFAULT '[]'::jsonb,
  "fetch"                JSONB NOT NULL,
  schedule               TEXT,
  credentials_ref        TEXT NOT NULL DEFAULT 'none',
  expected_row_count_sql TEXT,
  sla_seconds            INT  NOT NULL DEFAULT 3600
                           CHECK (sla_seconds > 0),
  manifest_path          TEXT,
  consumes               JSONB NOT NULL DEFAULT '{}'::jsonb,
  status                 TEXT NOT NULL DEFAULT 'stub'
                           CHECK (status IN ('stub', 'fetcher_ready', 'live')),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Lookup index for the dashboard "group by tier + domain" panel
-- (§J.3: dk-data-fe-source-registry). Cheap and covers the expected
-- filter patterns.
CREATE INDEX IF NOT EXISTS source_registry_domain_tier_idx
  ON meta.source_registry (domain, tier);

-- Status index for "stub vs live" rollup on the same dashboard.
CREATE INDEX IF NOT EXISTS source_registry_status_idx
  ON meta.source_registry (status);

COMMENT ON TABLE meta.source_registry IS
  'Declarative registry of onboarded data sources (plan §D.2). Rows '
  'projected from .dk/sources/<name>.yaml via '
  'python -m dk_data.ingestion.source_registry --sync.';

COMMENT ON COLUMN meta.source_registry."fetch" IS
  'Fetch descriptor — JSONB with at least {kind: postgres_dump|http_csv|'
  'http_json_paginated|zip|api_key} plus kind-specific fields '
  '(artifact_uri for postgres_dump, url for http_*).';

COMMENT ON COLUMN meta.source_registry.consumes IS
  'Budget reservation (plan §D.3) — e.g. {"wal_headroom_pct": 5, '
  '"db_connections": 2}. Enforcement in D.3.';

-- Grants: the hydration role writes (sync), PostgREST-facing roles read.
-- Use role-conditional DO blocks so the migration survives environments
-- where a role hasn't been provisioned yet (dev/staging boot order).
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sqlmesh') THEN
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON meta.source_registry TO sqlmesh';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'web_authenticator') THEN
    EXECUTE 'GRANT SELECT ON meta.source_registry TO web_authenticator';
  END IF;
END
$$;

COMMIT;
