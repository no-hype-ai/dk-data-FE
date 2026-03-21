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
    setid AS setid,              -- = drug_labels.spl_set_id
    NULL::UUID AS molecule_id,   -- filled by entity linking service

    -- DailyMed metadata
    spl_version,
    published_date,
    title,
    brand_name,
    generic_name,
    manufacturer,

    -- Source tracking
    source,
    source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at

FROM mol_bronze.dailymed
WHERE processed_to_silver = FALSE
  AND setid IS NOT NULL;
