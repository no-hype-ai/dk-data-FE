-- SQLMesh Model: Silver FDA Drugs (NDA/ANDA/BLA approvals)
-- Promotes mol_bronze.fda_drugs to silver, linking to mol_silver.molecules.
-- Feature: 019-cms-puf-platform-reconciliation
--
-- Grain: application_number
-- Source: mol_bronze.fda_drugs (from mol_raw.fda_drugs via FDADrugsFetcher)
-- Note: mol_silver.fda_drugsfda covers drug-specific lookups; this covers bulk approvals.

MODEL (
    name mol_silver.fda_drugs,
    kind FULL,
    cron '@weekly',
    audits (
        not_null(columns := (application_number))
    ),
    grain application_number
);

SELECT
    b.application_number,
    b.sponsor_name,
    b.application_type,
    b.brand_name,
    b.generic_name,
    b.dosage_form,
    b.route,
    b.marketing_status,
    b.te_code,
    b.reference_drug,
    b.reference_standard,
    m.molecule_id,
    b.ingested_at                       AS _ingested_at,
    CURRENT_TIMESTAMP                   AS _silver_updated_at
FROM mol_bronze.fda_drugs AS b
LEFT JOIN mol_silver.molecules AS m
    ON LOWER(TRIM(b.generic_name)) = LOWER(TRIM(m.inn_name))
    OR LOWER(TRIM(b.generic_name)) = LOWER(TRIM(m.preferred_name))
WHERE b.application_number IS NOT NULL
