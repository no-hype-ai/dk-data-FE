-- SQLMesh Model: Silver DailyMed Label Metadata
-- Links DailyMed SPL data to mol_silver.drug_labels via spl_set_id
-- Part of: 003-molecule-assessment-dashboard
--
-- Entity linking: setid (DailyMed) = spl_set_id (drug_labels)
-- This table enriches drug_labels with version currency and NLM metadata.
-- Not a replacement — drug_labels remains the primary label source.

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
    -- Resolve molecule_id via name matching: generic_name then brand_name
    -- against mol_silver.molecule_aliases (covers pref_name, canonical_name, synonyms).
    COALESCE(
        ma_generic.molecule_id,
        ma_brand.molecule_id
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
    dm.id AS bronze_id,
    dm.source,
    dm.source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at

FROM mol_bronze.dailymed dm
LEFT JOIN mol_silver.molecule_aliases ma_generic
    ON dm.generic_name IS NOT NULL
    AND LOWER(REGEXP_REPLACE(dm.generic_name, '[^a-zA-Z0-9]', '', 'g'))
       = ma_generic.alias_name_normalized
LEFT JOIN mol_silver.molecule_aliases ma_brand
    ON COALESCE(ma_generic.molecule_id, NULL) IS NULL
    AND dm.brand_name IS NOT NULL
    AND LOWER(REGEXP_REPLACE(dm.brand_name, '[^a-zA-Z0-9]', '', 'g'))
       = ma_brand.alias_name_normalized
WHERE dm.processed_to_silver = FALSE
  AND dm.setid IS NOT NULL;
