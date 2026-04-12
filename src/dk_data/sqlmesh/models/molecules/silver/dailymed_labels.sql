-- SQLMesh Model: Silver DailyMed Label Metadata
-- Links DailyMed SPL data to mol_silver.drug_labels via spl_set_id
-- Part of: 003-molecule-assessment-dashboard
--
-- Entity linking: setid (DailyMed) = spl_set_id (drug_labels)
-- This table enriches drug_labels with version currency and NLM metadata.
-- Not a replacement — drug_labels remains the primary label source.
--
-- Antipattern fixes (T133):
--   mol_silver.molecule_names replaced with mol_silver.molecule_names (normalized_name).
--   Deduplication subquery replaced with LATERAL JOIN + LIMIT 1 to avoid DISTINCT ON fanout.
--
-- FR-031 openfda.* linking (T133):
--   mol_bronze.dailymed does not yet have a typed openfda JSONB column.
--   openfda linkage (UNII→RxCUI) is implemented in mol_silver.drug_labels via
--   mol_bronze.openfda_labels which contains unii + rxcui arrays.
--   When mol_bronze.dailymed exposes openfda JSONB, activate the tiered LATERAL below:
--
--   LEFT JOIN LATERAL (
--       SELECT mi.molecule_id, 1 AS tier FROM mol_silver.molecule_identifiers mi
--       WHERE mi.source = 'unii' AND mi.identifier = dm.openfda->>'unii'
--       UNION ALL
--       SELECT mi.molecule_id, 2 AS tier FROM mol_silver.molecule_identifiers mi
--       WHERE mi.source = 'rxnorm' AND mi.identifier = dm.openfda->>'rxcui'
--       UNION ALL
--       SELECT mn.molecule_id, 3 AS tier FROM mol_silver.molecule_names mn
--       WHERE mn.normalized_name = LOWER(REGEXP_REPLACE(dm.generic_name, '[^a-zA-Z0-9]', '', 'g'))
--       UNION ALL
--       SELECT mn.molecule_id, 4 AS tier FROM mol_silver.molecule_names mn
--       WHERE mn.normalized_name = LOWER(REGEXP_REPLACE(dm.brand_name, '[^a-zA-Z0-9]', '', 'g'))
--       ORDER BY tier LIMIT 1
--   ) openfda_link ON TRUE
--
-- T118 verified: rewrite uses hub equi-join, zero S1-S5 antipatterns per test_silver_antipatterns.py

MODEL (
    name mol_silver.dailymed_labels,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key setid
    ),
    cron '@monthly',
    audits (
        not_null(columns := (setid))
    ),
    grain setid
);

SELECT
    gen_random_uuid() AS id,

    -- Entity linking key to drug_labels
    dm.setid AS setid,              -- = drug_labels.spl_set_id
    -- Resolve molecule_id via tiered name matching: generic_name then brand_name
    -- against mol_silver.molecule_names hub table (replaces mol_silver.molecule_names).
    -- When mol_bronze.dailymed exposes openfda JSONB, activate UNII/RxCUI tiers (see FR-031 comment above).
    COALESCE(
        mn_generic.molecule_id,
        mn_brand.molecule_id
    ) AS molecule_id,

    -- DailyMed metadata (all bronze columns)
    dm.spl_version,
    dm.published_date,
    dm.title,
    dm.brand_name,
    dm.generic_name,
    dm.manufacturer,
    dm.entity_link_key,
    dm.entity_link_type,
    dm.query_name,

    -- Source tracking
    dm.source,
    dm.source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at

FROM mol_bronze.dailymed dm
-- Tier 1: generic_name → molecule_names hub equi-join (replaces molecule_aliases)
LEFT JOIN LATERAL (
    SELECT mn.molecule_id
    FROM mol_silver.molecule_names mn
    WHERE dm.generic_name IS NOT NULL
      AND mn.normalized_name = LOWER(REGEXP_REPLACE(dm.generic_name, '[^a-zA-Z0-9]', '', 'g'))
    ORDER BY mn.molecule_id
    LIMIT 1
) mn_generic ON TRUE
-- Tier 2: brand_name → molecule_names hub equi-join (fallback when generic_name didn't match)
LEFT JOIN LATERAL (
    SELECT mn.molecule_id
    FROM mol_silver.molecule_names mn
    WHERE mn_generic.molecule_id IS NULL
      AND dm.brand_name IS NOT NULL
      AND mn.normalized_name = LOWER(REGEXP_REPLACE(dm.brand_name, '[^a-zA-Z0-9]', '', 'g'))
    ORDER BY mn.molecule_id
    LIMIT 1
) mn_brand ON TRUE
WHERE dm.processed_to_silver = FALSE
  AND dm.setid IS NOT NULL;
