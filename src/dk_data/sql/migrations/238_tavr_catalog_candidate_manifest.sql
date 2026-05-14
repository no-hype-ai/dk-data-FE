-- Migration 238: TAVR catalog candidate manifest
-- Spec: .dk/specs/006-tavr-catalog-candidate-manifest-provisioning/spec.md
-- Handoff: 2026-05-14-edwards-meadow-to-dk-data-fe-provision-tavr-catalog-candidate-manifest.md
-- Composite parent: 2026-05-13-edwards-meadow-to-dk-data-fe-confirm-hcs-tavr-gold-provisioning-ownership (closed)
--
-- Creates the bronze + silver + gold tables for Phase 0 of TAVR Benchmark Lab.
-- Phase 0 is catalog discovery — capture candidate public datasets from
-- Data.gov, CMS, HRSA, Census, USDA, CDC, FDA, SEC EDGAR, IRS, etc., classify
-- each by source/coverage/use class, surface drift between runs.
--
-- This migration creates the schema and indexes only. Fetchers + SQLMesh
-- promotion models land in subsequent migrations + k8s manifests.

BEGIN;

-- ----------------------------------------------------------------------------
-- Bronze: raw JSON payloads from each catalog API, one row per fetch event.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hcs_bronze.tavr_catalog_raw (
  id                    BIGSERIAL PRIMARY KEY,
  publisher             TEXT NOT NULL,                  -- "data_gov" | "cms" | "hrsa" | "census" | ...
  catalog_package_id    TEXT NOT NULL,                  -- publisher-scoped id
  raw                   JSONB NOT NULL,                 -- full API response payload
  search_query          TEXT,                           -- the query that surfaced this record
  fetched_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS tavr_catalog_raw_publisher_idx
  ON hcs_bronze.tavr_catalog_raw (publisher, fetched_at DESC);
CREATE INDEX IF NOT EXISTS tavr_catalog_raw_package_idx
  ON hcs_bronze.tavr_catalog_raw (publisher, catalog_package_id, fetched_at DESC);

COMMENT ON TABLE hcs_bronze.tavr_catalog_raw IS
  'Raw catalog discovery payloads. One row per (publisher, fetch). Silver dedupes by (publisher, catalog_package_id) keeping the newest fetched_at.';

-- ----------------------------------------------------------------------------
-- Silver: normalized, deduplicated catalog packages.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hcs_silver.tavr_catalog_packages (
  catalog_package_id    TEXT NOT NULL,
  publisher             TEXT NOT NULL,
  slug                  TEXT NOT NULL,
  title                 TEXT NOT NULL,
  access_level          TEXT NOT NULL,
  license               TEXT,
  temporal_coverage     TEXT,
  data_dictionary_url   TEXT,
  distribution_urls     JSONB NOT NULL DEFAULT '[]'::jsonb,
  search_query          TEXT,
  last_harvested_date   TIMESTAMPTZ NOT NULL,
  raw_id                BIGINT REFERENCES hcs_bronze.tavr_catalog_raw(id) ON DELETE SET NULL,
  PRIMARY KEY (publisher, catalog_package_id)
);

CREATE INDEX IF NOT EXISTS tavr_catalog_packages_slug_idx
  ON hcs_silver.tavr_catalog_packages (publisher, slug);
CREATE INDEX IF NOT EXISTS tavr_catalog_packages_harvest_idx
  ON hcs_silver.tavr_catalog_packages (last_harvested_date DESC);

COMMENT ON TABLE hcs_silver.tavr_catalog_packages IS
  'Deduplicated catalog packages. (publisher, catalog_package_id) is the natural key. distribution_urls is JSONB array of URLs.';

-- ----------------------------------------------------------------------------
-- Gold: the canonical catalog manifest with provenance discipline.
-- Every row carries the eight required columns (source_class, coverage_class,
-- use_class, grain, as_of_date, source_id, confidence, caveat_text). The
-- CHECK constraints encode the controlled vocabularies the recommendation
-- §Data Governance enforces.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hcs_gold.tavr_catalog_candidate_manifest (
  catalog_package_id      TEXT PRIMARY KEY,
  slug                    TEXT NOT NULL,
  title                   TEXT NOT NULL,
  publisher               TEXT NOT NULL,
  access_level            TEXT NOT NULL CHECK (access_level IN ('public', 'restricted', 'private')),
  license                 TEXT,
  temporal_coverage       TEXT,
  last_harvested_date     TIMESTAMPTZ NOT NULL,
  data_dictionary_url     TEXT,
  distribution_urls       JSONB NOT NULL DEFAULT '[]'::jsonb,
  search_query            TEXT,

  -- Provenance discipline — NOT NULL, controlled vocabularies.
  source_class            TEXT NOT NULL CHECK (source_class IN (
                            'public_machine_readable',
                            'public_abstractable',
                            'licensed_commercial',
                            'private_or_partner'
                          )),
  coverage_class          TEXT NOT NULL,
  use_class               TEXT NOT NULL,
  grain                   TEXT NOT NULL DEFAULT 'dataset_package'
                            CHECK (grain = 'dataset_package'),
  as_of_date              TIMESTAMPTZ NOT NULL,
  source_id               TEXT NOT NULL,
  confidence              NUMERIC(3,2) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  caveat_text             TEXT NOT NULL DEFAULT '',

  -- Lifecycle.
  review_state            TEXT NOT NULL DEFAULT 'catalog_discovered'
                            CHECK (review_state IN (
                              'catalog_discovered',
                              'under_review',
                              'promoted',
                              'rejected',
                              'superseded'
                            )),
  last_drift_detected_at  TIMESTAMPTZ,

  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS tavr_catalog_publisher_idx
  ON hcs_gold.tavr_catalog_candidate_manifest (publisher);
CREATE INDEX IF NOT EXISTS tavr_catalog_source_class_idx
  ON hcs_gold.tavr_catalog_candidate_manifest (source_class);
CREATE INDEX IF NOT EXISTS tavr_catalog_review_state_idx
  ON hcs_gold.tavr_catalog_candidate_manifest (review_state)
  WHERE review_state <> 'promoted';

COMMENT ON TABLE hcs_gold.tavr_catalog_candidate_manifest IS
  'Phase 0 catalog of public-dataset candidates for the TAVR Benchmark Lab. Every row carries the provenance-discipline NOT NULL set (source_class, coverage_class, use_class, grain, as_of_date, source_id, confidence, caveat_text). See .dk/specs/006-tavr-catalog-candidate-manifest-provisioning/spec.md.';

-- ----------------------------------------------------------------------------
-- meta: catalog drift events keyed by catalog_package_id. Populated by the
-- silver→gold promotion model whenever a previously-seen package's
-- distribution_urls or publisher metadata mutates.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meta.catalog_drift_events (
  id                  BIGSERIAL PRIMARY KEY,
  catalog_package_id  TEXT NOT NULL,
  publisher           TEXT NOT NULL,
  drift_kind          TEXT NOT NULL CHECK (drift_kind IN (
                        'distribution_url_changed',
                        'publisher_metadata_changed',
                        'license_changed',
                        'access_level_changed'
                      )),
  prev_value          JSONB,
  new_value           JSONB,
  detected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS catalog_drift_events_pkg_idx
  ON meta.catalog_drift_events (publisher, catalog_package_id, detected_at DESC);

COMMENT ON TABLE meta.catalog_drift_events IS
  'Append-only log of catalog-package drift between harvests. Surfaces stale distribution URLs and changed publisher metadata for downstream triage.';

-- ----------------------------------------------------------------------------
-- Permissions: edwards-meadow consumer (alias `em`) is registered in
-- k8s/apps/metering-proxy/base/configmap.yaml with allowed_schemas =
-- [hcs_silver, hcs_gold, meta]. PostgREST role `readonly` (the JWT path)
-- and `api_user` (the metering-proxy path) both need SELECT on these tables.
-- ----------------------------------------------------------------------------
DO $perms$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'readonly') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA hcs_silver, hcs_gold, meta TO readonly';
    EXECUTE 'GRANT SELECT ON hcs_silver.tavr_catalog_packages TO readonly';
    EXECUTE 'GRANT SELECT ON hcs_gold.tavr_catalog_candidate_manifest TO readonly';
    EXECUTE 'GRANT SELECT ON meta.catalog_drift_events TO readonly';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_user') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA hcs_silver, hcs_gold, meta TO api_user';
    EXECUTE 'GRANT SELECT ON hcs_silver.tavr_catalog_packages TO api_user';
    EXECUTE 'GRANT SELECT ON hcs_gold.tavr_catalog_candidate_manifest TO api_user';
    EXECUTE 'GRANT SELECT ON meta.catalog_drift_events TO api_user';
  END IF;
END $perms$;

COMMIT;
