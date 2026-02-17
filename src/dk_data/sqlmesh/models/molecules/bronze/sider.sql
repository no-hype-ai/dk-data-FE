-- SQLMesh Model: Bronze SIDER
-- Transforms raw SIDER side effects data into typed bronze layer
-- SIDER contains drug-side effect associations from package inserts
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name bronze.sider,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        lookback 7
    ),
    cron '@monthly',
    grain (stitch_id, meddra_concept_id),
    audits (
        not_null(columns := (stitch_id))
    )
);

SELECT
    uuid_generate_v4() AS id,
    r.id AS raw_id,

    -- Drug identification (STITCH ID format: CID + stereo prefix)
    COALESCE(
        r.response_body->>'stitch_id_flat',
        r.response_body->>'stitch_id'
    ) AS stitch_id,
    -- Extract PubChem CID from STITCH ID (remove prefix)
    CASE
        WHEN r.response_body->>'stitch_id_flat' IS NOT NULL
        THEN REGEXP_REPLACE(r.response_body->>'stitch_id_flat', '^CID[sm]?', '')
        WHEN r.response_body->>'stitch_id' IS NOT NULL
        THEN REGEXP_REPLACE(r.response_body->>'stitch_id', '^CID[sm]?', '')
        ELSE NULL
    END AS pubchem_cid,
    COALESCE(
        r.response_body->>'drug_name',
        r.response_body->>'name'
    ) AS drug_name,

    -- Side effect identification (MedDRA)
    COALESCE(
        r.response_body->>'meddra_concept_id',
        r.response_body->>'umls_concept_id',
        r.response_body->>'side_effect_id'
    ) AS meddra_concept_id,
    COALESCE(
        r.response_body->>'meddra_concept_name',
        r.response_body->>'side_effect_name',
        r.response_body->>'side_effect'
    ) AS side_effect_name,
    r.response_body->>'meddra_level' AS meddra_level,

    -- Frequency information
    COALESCE(
        r.response_body->>'frequency',
        r.response_body->>'freq'
    ) AS frequency_raw,
    CASE
        WHEN r.response_body->>'frequency' ~ '^[\d.]+%$'
        THEN (REGEXP_REPLACE(r.response_body->>'frequency', '%', ''))::NUMERIC / 100
        WHEN r.response_body->>'frequency_lower' IS NOT NULL
        THEN (r.response_body->>'frequency_lower')::NUMERIC
        ELSE NULL
    END AS frequency_lower,
    CASE
        WHEN r.response_body->>'frequency_upper' IS NOT NULL
        THEN (r.response_body->>'frequency_upper')::NUMERIC
        ELSE NULL
    END AS frequency_upper,
    r.response_body->>'frequency_description' AS frequency_description,

    -- Placebo comparison (if available)
    CASE
        WHEN r.response_body->>'placebo_frequency' ~ '^[\d.]+$'
        THEN (r.response_body->>'placebo_frequency')::NUMERIC
        ELSE NULL
    END AS placebo_frequency,

    -- Source indication
    r.response_body->>'indication_source' AS indication_source,
    r.response_body->>'indication' AS indication,

    -- Classification
    CASE
        WHEN r.response_body->>'side_effect_type' IS NOT NULL
        THEN r.response_body->>'side_effect_type'
        WHEN (r.response_body->>'frequency_lower')::NUMERIC > 0.1 THEN 'very_common'
        WHEN (r.response_body->>'frequency_lower')::NUMERIC > 0.01 THEN 'common'
        WHEN (r.response_body->>'frequency_lower')::NUMERIC > 0.001 THEN 'uncommon'
        WHEN (r.response_body->>'frequency_lower')::NUMERIC > 0.0001 THEN 'rare'
        ELSE 'very_rare'
    END AS frequency_category,

    -- Processing metadata
    FALSE AS processed_to_silver,
    NOW() AS ingested_at

FROM raw.sider r
WHERE r.response_status = 200
  AND r.processed_to_bronze = FALSE
  AND r.response_body IS NOT NULL
  AND COALESCE(
      r.response_body->>'stitch_id_flat',
      r.response_body->>'stitch_id'
  ) IS NOT NULL
