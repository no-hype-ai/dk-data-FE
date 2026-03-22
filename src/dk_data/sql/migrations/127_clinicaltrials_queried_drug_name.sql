-- Migration 127: Add queried_drug_name to mol_bronze.clinicaltrials
-- Date: 2026-03-22
-- Feature: 003-molecule-assessment-dashboard / 012-dk-data-platform
--
-- Problem: The bronze clinicaltrials transform was using fuzzy ILIKE matching on trial
--   titles to link trials to molecules. This caused cross-contamination (e.g. trials
--   for "trastuzumab" matching "trastuzumab deruxtecan" and vice versa) and failed to
--   link trials for molecules with needs_review=TRUE (durvalumab, trastuzumab deruxtecan,
--   nivolumab and relatlimab).
--
-- Fix: Store the drug name that was used in the original ClinicalTrials API query
--   (request_params->>'query.intr') as queried_drug_name on each bronze row.
--   The silver entity linking JOIN now uses queried_drug_name as the primary signal
--   and fuzzy matching only as fallback. Most-specific (longest) canonical_name wins
--   when multiple drugs match (handles "trastuzumab" vs "trastuzumab deruxtecan").
--
-- Schema changes:
--   mol_bronze.mol_bronze__clinicaltrials__571789171: ADD COLUMN queried_drug_name TEXT
--   mol_bronze.clinicaltrials (view): recreated with SELECT * to expose new column
--   mol_silver.*__clinical_trials__*: ADD COLUMN queried_drug_name TEXT (all versions)
--   mol_silver.clinical_trials (view): recreated with SELECT * to expose new column
--
-- SQLMesh model changes (already in .sql files, this migration covers live tables):
--   models/molecules/bronze/clinicaltrials.sql: CTE now extracts queried_drug_name
--     from request_params->>'query.intr'; DISTINCT ON(nct_id) deduplicates results
--     that appear across multiple search pages
--   models/molecules/silver/clinical_trials.sql: entity linking ORDER BY updated to
--     prefer exact queried_drug_name match, then partial match, then fuzzy fallback;
--     LENGTH(canonical_name) DESC ensures more-specific drugs win over parent names

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Bronze physical table: add queried_drug_name
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE mol_bronze."mol_bronze__clinicaltrials__571789171"
    ADD COLUMN IF NOT EXISTS queried_drug_name TEXT;

-- Backfill from the original raw API request params
UPDATE mol_bronze."mol_bronze__clinicaltrials__571789171" b
SET queried_drug_name = raw.request_params->>'query.intr'
FROM mol_raw.clinicaltrials raw
WHERE b.raw_source_id = raw.id
  AND raw.request_params->>'query.intr' IS NOT NULL
  AND b.queried_drug_name IS NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Bronze view: recreate with SELECT * so new column is exposed to silver model
--    and PostgREST
-- ─────────────────────────────────────────────────────────────────────────────

DROP VIEW IF EXISTS mol_bronze.clinicaltrials;

CREATE VIEW mol_bronze.clinicaltrials AS
SELECT * FROM mol_bronze."mol_bronze__clinicaltrials__571789171";

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Silver physical tables: add queried_drug_name to all versions so SQLMesh
--    FULL-refresh inserts land correctly regardless of which snapshot is active
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE mol_silver."mol_silver__clinical_trials__3417801811"
    ADD COLUMN IF NOT EXISTS queried_drug_name TEXT;
ALTER TABLE mol_silver."mol_silver__clinical_trials__3728829754"
    ADD COLUMN IF NOT EXISTS queried_drug_name TEXT;
ALTER TABLE mol_silver."mol_silver__clinical_trials__3994358123"
    ADD COLUMN IF NOT EXISTS queried_drug_name TEXT;
ALTER TABLE mol_silver."mol_silver__clinical_trials__4172522036"
    ADD COLUMN IF NOT EXISTS queried_drug_name TEXT;
ALTER TABLE mol_silver."mol_silver__clinical_trials__560523345"
    ADD COLUMN IF NOT EXISTS queried_drug_name TEXT;

-- Backfill silver from bronze
UPDATE mol_silver."mol_silver__clinical_trials__560523345" ct
SET queried_drug_name = b.queried_drug_name
FROM mol_bronze.clinicaltrials b
WHERE ct.nct_id = b.nct_id
  AND b.queried_drug_name IS NOT NULL
  AND ct.queried_drug_name IS NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Silver view: recreate with SELECT * to expose queried_drug_name via PostgREST
-- ─────────────────────────────────────────────────────────────────────────────

DROP VIEW IF EXISTS mol_silver.clinical_trials;

CREATE VIEW mol_silver.clinical_trials AS
SELECT * FROM mol_silver."mol_silver__clinical_trials__560523345";

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. Also fix needs_review for any molecules onboarded before this migration
--    that are stuck with needs_review=TRUE (blocks entity linking JOIN)
-- ─────────────────────────────────────────────────────────────────────────────

UPDATE mol_silver.molecules
SET needs_review = FALSE,
    review_reason = NULL
WHERE needs_review = TRUE
  AND review_reason = 'auto-onboarded';

COMMIT;
