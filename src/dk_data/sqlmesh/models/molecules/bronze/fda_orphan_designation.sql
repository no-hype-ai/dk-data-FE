-- SQLMesh Model: Bronze FDA Orphan Drug Designations
-- Simple passthrough from mol_raw.fda_orphan_designation
-- Feature: 006-claims-engine-data-gaps (T018)
-- Source: FDA Orphan Drug Designations and Approvals

MODEL (
    name mol_bronze.fda_orphan_designation,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key designation_number
    ),
    cron '@weekly',
    audits (
        not_null(columns := (designation_number))
    ),
    grain designation_number
);

SELECT DISTINCT ON (designation_number)
    gen_random_uuid()                   AS id,
    designation_number,
    generic_name,
    trade_name,
    sponsor,
    designation_date,
    designated_indication,
    marketing_approval_date,
    ingested_at,
    ingested_at                         AS source_updated_at,
    'fda_orphan_designation'            AS source,
    FALSE                               AS processed_to_silver,
    NOW()                               AS created_at
FROM mol_raw.fda_orphan_designation
WHERE designation_number IS NOT NULL
ORDER BY designation_number, ingested_at DESC NULLS LAST;
