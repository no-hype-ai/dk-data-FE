-- SQLMesh Model: Silver REMS Programs
-- FDA Risk Evaluation and Mitigation Strategy (REMS) program requirements.
-- Feature: 019-cms-puf-platform-reconciliation
--
-- Source: mol_bronze.fda_rems (from mol_raw.fda_rems via FDARemsFetcher)
-- Entity linking:
--   molecule_id: (3-tier COALESCE)
--     1. generic_name → molecule_aliases (normalized exact match)
--     2. brand_name   → molecule_aliases (normalized exact match)
--     3. generic_name with salt suffix stripped → molecule_aliases
--        Handles: "Morphine Sulfate" → "Morphine", "Alosetron HCl" → "Alosetron",
--                 "Hydrocodone AND Acetaminophen" → "Hydrocodone" (first active)
--
-- Grain: (molecule_id, application_number)

MODEL (
    name mol_silver.rems_programs,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (molecule_id, application_number)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (application_number))
    ),
    grain (molecule_id, application_number)
);

SELECT
    gen_random_uuid()                                               AS rems_id,

    -- molecule_id: 3-tier lookup
    COALESCE(
        -- Tier 1: exact normalized generic_name match
        (SELECT ma.molecule_id FROM mol_silver.molecule_aliases ma
         WHERE LOWER(REGEXP_REPLACE(b.generic_name, '[^a-zA-Z0-9]', '', 'g')) = ma.alias_name_normalized
         LIMIT 1),
        -- Tier 2: exact normalized brand_name match
        (SELECT ma.molecule_id FROM mol_silver.molecule_aliases ma
         WHERE LOWER(REGEXP_REPLACE(b.brand_name, '[^a-zA-Z0-9]', '', 'g')) = ma.alias_name_normalized
         LIMIT 1),
        -- Tier 3: salt/combination normalization on generic_name
        -- Strips common pharmaceutical salt suffixes (e.g. "Morphine Sulfate" → "Morphine")
        -- and combination suffixes (e.g. "Hydrocodone AND Acetaminophen" → "Hydrocodone")
        (SELECT ma.molecule_id FROM mol_silver.molecule_aliases ma
         WHERE LOWER(REGEXP_REPLACE(
             REGEXP_REPLACE(
                 REGEXP_REPLACE(b.generic_name,
                     '\s+(HYDROCHLORIDE|HCL|SULFATE|SODIUM|POTASSIUM|PHOSPHATE|BITARTRATE|TARTRATE|ACETATE|MALEATE|FUMARATE|SUCCINATE|CITRATE|BROMIDE|MESYLATE|TOSYLATE|BESYLATE|OXALATE|GLUCONATE|LACTATE|MALATE|NITRATE|DIHYDRATE|MONOHYDRATE|HEMIHYDRATE)\s*$',
                     '', 'i'),
                 '\s+(AND|WITH)\s+.*$', '', 'i'),
             '[^a-zA-Z0-9]', '', 'g')) = ma.alias_name_normalized
         LIMIT 1)
    )                                                               AS molecule_id,

    b.brand_name,
    b.generic_name,
    b.application_number,
    b.application_type,
    b.sponsor_name,
    b.rems_type,
    b.initial_approval_date,
    b.most_recent_modification,
    b.rems_status,
    b.elements,
    b.url,
    b.source,
    b.source_updated_at,
    b.ingested_at,
    NOW()                                                           AS created_at

FROM mol_bronze.fda_rems b
WHERE b.application_number IS NOT NULL
  AND b.processed_to_silver = FALSE;
