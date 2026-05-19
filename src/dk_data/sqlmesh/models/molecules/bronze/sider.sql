-- SQLMesh Model: Bronze SIDER
-- Transforms raw SIDER side effects data into typed bronze layer
-- SIDER contains drug-side effect associations extracted from package inserts
-- Part of DK Molecule Data Platform (012-dk-data-platform)
--
-- SIDER data is sourced from two TSV files stored as JSONB in mol_raw.sider:
--
-- meddra_all_se.tsv fields:
--   stitch_id_flat       — flat STITCH compound ID (CIDmNNNNNNNN)
--   stitch_id_stereo     — stereo STITCH compound ID (CIDsNNNNNNNN)
--   umls_cui_side_effect — UMLS CUI for the side effect
--   side_effect_name     — plain-text side effect name
--
-- meddra_freq.tsv additional fields:
--   placebo              — 'placebo' if placebo-only side effect
--   frequency            — frequency string (e.g. "postmarketing", "0.1-1")
--   lower_bound_freq     — lower bound frequency (0.0–1.0 proportion)
--   upper_bound_freq     — upper bound frequency (0.0–1.0 proportion)
--   meddra_concept_type  — MedDRA concept type (PT, LLT, HLT, HLGT, SOC)
--   umls_cui_from_label  — UMLS CUI from the label text
--   side_effect_name     — plain-text side effect name

MODEL (
    name mol_bronze.sider,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (stitch_id_flat, umls_cui_side_effect)
    ),
    cron '@monthly',
    grain (stitch_id_flat, umls_cui_side_effect),
    audits (
        not_null(columns := (stitch_id_flat))
    )
);

SELECT
    uuid_generate_v4() AS id,
    r.id AS raw_id,

    -- Drug identification using STITCH IDs
    -- Flat ID format: CIDmNNNNNNNN (merged stereochemistry)
    r.response_body->>'stitch_id_flat' AS stitch_id_flat,
    -- Stereo ID format: CIDsNNNNNNNN (specific stereoisomer)
    r.response_body->>'stitch_id_stereo' AS stitch_id_stereo,

    -- Extract numeric PubChem CID from flat STITCH ID
    -- CIDm prefix + 9-digit zero-padded CID → strip prefix and leading zeros
    CASE
        WHEN r.response_body->>'stitch_id_flat' ~ '^CIDm\d+$'
        THEN LTRIM(REGEXP_REPLACE(r.response_body->>'stitch_id_flat', '^CIDm0*', ''), '0')::BIGINT
        ELSE NULL
    END AS pubchem_cid,

    -- Side effect identification using UMLS CUIs
    r.response_body->>'umls_cui_side_effect' AS umls_cui_side_effect,
    r.response_body->>'side_effect_name' AS side_effect_name,

    -- MedDRA concept type (from meddra_freq.tsv: PT, LLT, HLT, HLGT, SOC)
    r.response_body->>'meddra_concept_type' AS meddra_concept_type,
    -- UMLS CUI as mapped from the label text (may differ from umls_cui_side_effect)
    r.response_body->>'umls_cui_from_label' AS umls_cui_from_label,

    -- Frequency information (from meddra_freq.tsv)
    r.response_body->>'placebo' AS placebo,
    r.response_body->>'frequency' AS frequency_raw,

    -- Numeric frequency bounds (stored as proportions 0.0–1.0 in SIDER)
    CASE
        WHEN r.response_body->>'lower_bound_freq' ~ '^[\d.]+$'
        THEN (r.response_body->>'lower_bound_freq')::NUMERIC
        ELSE NULL
    END AS lower_bound_freq,
    CASE
        WHEN r.response_body->>'upper_bound_freq' ~ '^[\d.]+$'
        THEN (r.response_body->>'upper_bound_freq')::NUMERIC
        ELSE NULL
    END AS upper_bound_freq,

    -- Derived frequency category from lower_bound_freq
    CASE
        WHEN (r.response_body->>'lower_bound_freq')::NUMERIC > 0.1 THEN 'very_common'
        WHEN (r.response_body->>'lower_bound_freq')::NUMERIC > 0.01 THEN 'common'
        WHEN (r.response_body->>'lower_bound_freq')::NUMERIC > 0.001 THEN 'uncommon'
        WHEN (r.response_body->>'lower_bound_freq')::NUMERIC > 0.0001 THEN 'rare'
        WHEN (r.response_body->>'lower_bound_freq')::NUMERIC IS NOT NULL THEN 'very_rare'
        ELSE NULL
    END AS frequency_category,

    -- Source TSV file identifier stored by the loader
    r.response_body->>'source_file' AS source_file,

    -- Processing metadata
    FALSE AS processed_to_silver,
    r.ingested_at

FROM mol_raw.sider r
WHERE r.response_status = 200
  AND r.processed_to_bronze = FALSE
  AND r.response_body IS NOT NULL
  AND r.response_body->>'stitch_id_flat' IS NOT NULL
  AND r.ingested_at BETWEEN @start_dt AND @end_dt
