-- Migration: 216_missing_mol_api_views
-- Feature: 002-external-integration-foundation (US-4, T071 — REVISED SCOPE)
-- Purpose: Create the one mol_api view that is a genuinely new aggregation,
--          not a rename or a duplication of an existing silver table:
--
--            mol_api.competitive_scores — derived numeric score from
--            mol_gold.competitive_landscape
--
-- Architectural correction: The original feature 002 plan listed 5 missing
-- mol_api views. Inspection of the silver layer found that 4 of them are
-- redundant with tables that already exist:
--
--   mol_api.boxed_warnings      → redundant, mol_silver.drug_labels has
--                                  the inline `boxed_warning` column;
--                                  consumers can filter directly against it
--                                  (`?boxed_warning=not.is.null`)
--   mol_api.contraindications   → same: mol_silver.drug_labels.contraindications
--   mol_api.companies           → redundant, mol_silver.companies already
--                                  exists as a full silver hub with
--                                  company_identifiers + company_names
--   mol_api.publications        → redundant, mol_silver.publications and
--                                  mol_silver.pubmed_articles already cover
--                                  the unified + per-source use cases
--
-- Only `mol_api.competitive_scores` remains, because it is a NEW derived
-- aggregation applying a scoring formula on top of mol_gold.competitive_
-- landscape. It is not a rename of anything that already exists; it adds
-- value that the silver/gold layer does not provide directly.
--
-- The four dropped views are handled in migration 215_deprecate_redundant_
-- ci_views.sql (which also marks the api.* CI views as deprecated in favor
-- of their silver equivalents). Consumers who want boxed warnings or
-- contraindications query `mol_silver.drug_labels` directly. Consumers who
-- want companies or publications query `mol_silver.companies` and
-- `mol_silver.publications` directly. Both silver schemas are already in
-- PGRST_DB_SCHEMAS and already granted to analyst.
--
-- Run: psql -h localhost -p 5433 -U postgres -d dk_data -f migrations/216_missing_mol_api_views.sql

BEGIN;

SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '10s';

-- Ensure mol_api exists (should already, from migration 020_mol_schemas.sql).
CREATE SCHEMA IF NOT EXISTS mol_api;
GRANT USAGE ON SCHEMA mol_api TO analyst, api_user;

-- -----------------------------------------------------------------------------
-- mol_gold.competitive_landscape
--
-- Migration 081 created this table; migration 144 dropped it as part of a
-- legacy-bronze cleanup that inadvertently caught this gold table too. This
-- migration re-creates it (idempotently) so mol_api.competitive_scores has
-- a stable source to query.
--
-- Schema mirrors the version in 081 with the addition of active_trials,
-- total_trials, sponsor_count, canonical_name, inchi_key, therapeutic_areas,
-- indications, and sponsors — the fields actually needed by competitive_scores.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS mol_gold.competitive_landscape (
    id                  TEXT PRIMARY KEY,
    molecule_id         TEXT,
    inchi_key           TEXT,
    canonical_name      TEXT,
    indication          TEXT,
    therapeutic_areas   TEXT[],
    development_status  TEXT,
    max_phase           INTEGER,
    active_trials       INTEGER,
    total_trials        INTEGER,
    sponsor_count       INTEGER,
    indications         TEXT[],
    sponsors            TEXT[],
    snapshot_date       DATE DEFAULT CURRENT_DATE,
    computed_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (molecule_id, indication, snapshot_date)
);

COMMENT ON TABLE mol_gold.competitive_landscape IS
    'Gold-layer competitive landscape snapshot per molecule × indication × date. '
    'Source of truth for mol_api.competitive_scores. Dropped by migration 144 '
    '(legacy cleanup overshoot) and recreated by migration 216.';

GRANT SELECT ON mol_gold.competitive_landscape TO analyst, api_user;

-- -----------------------------------------------------------------------------
-- mol_api.competitive_scores
--
-- Numeric competitive positioning score derived from
-- mol_gold.competitive_landscape. Score weights reflect late-stage
-- clinical development + active-trial activity:
--
--   approved (max_phase >= 4)  → 10
--   phase 3                     → 5
--   phase 2                     → 2
--   phase 1                     → 1
--   preclinical                 → 0
--
-- Plus a momentum bonus of 0.5 * ln(1 + active_trials) to reflect ongoing
-- clinical activity. Treat the score as a comparative ranking signal only.
-- -----------------------------------------------------------------------------

CREATE OR REPLACE VIEW mol_api.competitive_scores AS
SELECT
    cl.molecule_id,
    cl.inchi_key,
    cl.canonical_name,
    cl.therapeutic_areas,
    cl.development_status,
    cl.max_phase,
    cl.active_trials,
    cl.total_trials,
    cl.sponsor_count,
    cl.indications,
    cl.sponsors,
    (
        CASE
            WHEN cl.max_phase >= 4 THEN 10.0
            WHEN cl.max_phase = 3  THEN 5.0
            WHEN cl.max_phase = 2  THEN 2.0
            WHEN cl.max_phase = 1  THEN 1.0
            ELSE 0.0
        END
        + 0.5 * LN(1 + COALESCE(cl.active_trials, 0))
    )::NUMERIC(6, 2) AS competitive_score,
    cl.computed_at
FROM mol_gold.competitive_landscape cl;

COMMENT ON VIEW mol_api.competitive_scores IS
    'Numeric competitive positioning score derived from mol_gold.competitive_landscape. Score formula: 10 for approved (max_phase >= 4), 5 for phase 3, 2 for phase 2, 1 for phase 1, 0 otherwise, plus 0.5*ln(1+active_trials). Treat as comparative ranking, not absolute. Created by feature 002-external-integration-foundation US-4.';

GRANT SELECT ON mol_api.competitive_scores TO analyst, api_user;

-- -----------------------------------------------------------------------------
-- COMPLETION
-- -----------------------------------------------------------------------------

DO $$
BEGIN
    RAISE NOTICE '216_missing_mol_api_views complete: mol_api.competitive_scores created';
    RAISE NOTICE 'Note: the originally-planned boxed_warnings, contraindications, companies, and publications views were dropped as redundant — consumers read mol_silver.drug_labels, mol_silver.companies, and mol_silver.publications directly.';
END
$$;

COMMIT;
