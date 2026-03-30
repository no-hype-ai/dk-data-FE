-- SQLMesh Model: Silver REMS Programs
-- FDA Risk Evaluation and Mitigation Strategy (REMS) program requirements.
-- Feature: 019-cms-puf-platform-reconciliation
--
-- Source: mol_bronze.fda_rems (from mol_raw.fda_rems via FDARemsFetcher)
-- Entity linking:
--   molecule_id: generic_name → molecule_aliases (normalized exact match)
--               OR brand_name → molecule_aliases fallback
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

    -- molecule_id: generic_name alias match → brand_name alias fallback
    COALESCE(
        (SELECT ma.molecule_id FROM mol_silver.molecule_aliases ma
         WHERE LOWER(REGEXP_REPLACE(b.generic_name, '[^a-zA-Z0-9]', '', 'g')) = ma.alias_name_normalized
         LIMIT 1),
        (SELECT ma.molecule_id FROM mol_silver.molecule_aliases ma
         WHERE LOWER(REGEXP_REPLACE(b.brand_name, '[^a-zA-Z0-9]', '', 'g')) = ma.alias_name_normalized
         LIMIT 1)
    )                                                               AS molecule_id,

    b.brand_name,
    b.generic_name,
    b.application_number,
    b.rems_type,
    b.initial_approval_date,
    b.most_recent_modification,
    b.rems_status,
    b.elements,
    b.url,
    b.source,
    NOW()                                                           AS created_at

FROM mol_bronze.fda_rems b
WHERE b.application_number IS NOT NULL
  AND b.processed_to_silver = FALSE;
