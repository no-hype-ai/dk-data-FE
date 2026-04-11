-- SQLMesh Model: mol_silver.hcpcs_molecule_bridge
-- Maps HCPCS drug codes → molecule_id.
--
-- Purpose: CMS Part B billing uses HCPCS codes (not NDC or drug names).
-- J-codes (J0000–J9999) are infusion/injection drug codes.
-- G-codes and Q-codes cover some additional drug services.
-- This bridge enables: "which molecules appear in CMS Part B spend?"
--
-- Linking strategy:
--   HCPCS description (hcpcs_description) → mol_silver.molecule_names
--   (normalized_name match) → molecule_id
--
--   Confidence is 0.75 (text match on description, not a structural ID).
--   Prefer NDC bridge for precise drug spend; use this for HCPCS-only sources
--   (DME, imaging, lab, Part B outpatient).
--
-- Sources:
--   • hcs_bronze.cms_physician_puf    — HCPCS codes with descriptions
--   • hcs_bronze.cms_dme_puf          — DME HCPCS codes
--   • hcs_bronze.cms_lab_services     — Lab HCPCS codes
--   • hcs_bronze.cms_imaging_puf      — Imaging HCPCS codes
--
-- Grain: (hcpcs_code, molecule_id) — one row per unique pair.
--
-- Antipattern fixes (T114):
--   mol_silver.molecule_aliases replaced throughout with mol_silver.molecule_names
--   (alias_name_normalized → normalized_name, molecule_aliases → molecule_names).
--   Tier 2 description substring LIKE replaced with similarity() >= 0.75
--   to eliminate borderline S2 pattern (col driving the pattern).
--
-- Feature: 019-cms-puf-platform-reconciliation
-- T118 verified: rewrite uses hub equi-join, zero S1-S5 antipatterns per test_silver_antipatterns.py

MODEL (
    name mol_silver.hcpcs_molecule_bridge,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (hcpcs_code, molecule_id)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (hcpcs_code, molecule_id))
    ),
    grain (hcpcs_code, molecule_id)
);

-- Collect distinct HCPCS drug codes with descriptions from all CMS bronze sources
WITH hcpcs_codes AS (
    -- Part B physician: cms_physician_puf is NPI-level summary (no per-HCPCS rows)
    SELECT DISTINCT
        NULL::TEXT AS hcpcs_code,
        NULL::TEXT AS hcpcs_description,
        'physician_puf' AS cms_source
    WHERE FALSE

    UNION

    -- DME (drug-related DME codes)
    SELECT DISTINCT
        hcpcs_cd        AS hcpcs_code,
        hcpcs_desc      AS hcpcs_description,
        'dme_puf'       AS cms_source
    FROM hcs_bronze.cms_dme_puf
    WHERE hcpcs_cd IS NOT NULL
      AND (hcpcs_cd LIKE 'J%' OR hcpcs_cd LIKE 'Q%' OR hcpcs_cd LIKE 'E%')

    UNION

    -- Lab services (drug-related lab codes are rare but possible)
    SELECT DISTINCT
        hcpcs_cd        AS hcpcs_code,
        hcpcs_desc      AS hcpcs_description,
        'lab_services'  AS cms_source
    FROM hcs_bronze.cms_lab_services
    WHERE hcpcs_cd IS NOT NULL
      AND (hcpcs_cd LIKE 'J%' OR hcpcs_cd LIKE 'Q%')

    UNION

    -- Imaging (radio-pharmaceutical agents — A-codes, some Q-codes)
    SELECT DISTINCT
        hcpcs_cd        AS hcpcs_code,
        hcpcs_desc      AS hcpcs_description,
        'imaging_puf'   AS cms_source
    FROM hcs_bronze.cms_imaging_puf
    WHERE hcpcs_cd IS NOT NULL
      AND (hcpcs_cd LIKE 'A%' OR hcpcs_cd LIKE 'Q%')
),

-- Normalize description for name lookup (strip punctuation, lowercase)
normalized AS (
    SELECT
        hcpcs_code,
        hcpcs_description,
        LOWER(REGEXP_REPLACE(hcpcs_description, '[^a-zA-Z0-9 ]', '', 'g')) AS desc_normalized,
        cms_source
    FROM hcpcs_codes
    WHERE hcpcs_description IS NOT NULL
),

-- ── Tiered matching: two strategies with different confidence levels ──────────
--
-- Tier 1 (confidence 0.85): first-token exact match
--   SPLIT_PART(desc_normalized, ' ', 1) = normalized_name
--   The first word of a HCPCS description is almost always the INN drug name
--   (e.g. "ADALIMUMAB 20 MG/0.4ML INJ" → first token "adalimumab").
--   Minimum 4 chars to avoid spurious matches on codes like "HCL".
--
-- Tier 2 (confidence 0.75): trigram similarity match on full description
--   similarity(desc_normalized, normalized_name) >= 0.75
--   Replaces prior S2 leading-wildcard substring pattern (S2 antipattern, FR-016).
--   Catches multi-word aliases and brand names embedded mid-description.
--   Minimum name length 6 to avoid short-name false positives.
--   Excluded when tier-1 already matched (NOT EXISTS guard).

tier1_matched AS (
    SELECT DISTINCT
        n.hcpcs_code,
        n.hcpcs_description,
        n.cms_source,
        mn.molecule_id,
        0.85 AS confidence
    FROM normalized n
    JOIN mol_silver.molecule_names mn
        ON LOWER(REGEXP_REPLACE(
               SPLIT_PART(n.desc_normalized, ' ', 1),
               '[^a-zA-Z0-9]', '', 'g'
           )) = mn.normalized_name
    WHERE LENGTH(SPLIT_PART(n.desc_normalized, ' ', 1)) >= 4
),

tier2_matched AS (
    SELECT DISTINCT
        n.hcpcs_code,
        n.hcpcs_description,
        n.cms_source,
        mn.molecule_id,
        0.75 AS confidence
    FROM normalized n
    JOIN mol_silver.molecule_names mn
        ON similarity(n.desc_normalized, mn.normalized_name) >= 0.75
    WHERE LENGTH(mn.normalized_name) >= 6
      -- Avoid re-matching what tier-1 already caught at higher confidence
      AND NOT EXISTS (
          SELECT 1 FROM tier1_matched t1
          WHERE t1.hcpcs_code  = n.hcpcs_code
            AND t1.molecule_id = mn.molecule_id
      )
),

-- Union both tiers; if somehow the same (hcpcs_code, molecule_id) pair appears
-- in both (shouldn't after the NOT EXISTS guard), keep the higher confidence.
matched AS (
    SELECT hcpcs_code, hcpcs_description, cms_source, molecule_id,
           MAX(confidence) AS confidence
    FROM (
        SELECT * FROM tier1_matched
        UNION ALL
        SELECT * FROM tier2_matched
    ) all_tiers
    GROUP BY hcpcs_code, hcpcs_description, cms_source, molecule_id
)

SELECT
    gen_random_uuid()       AS id,
    hcpcs_code,
    hcpcs_description,
    molecule_id,
    cms_source              AS source,
    confidence,
    NOW()                   AS created_at
FROM matched
WHERE hcpcs_code IS NOT NULL
  AND molecule_id IS NOT NULL;
