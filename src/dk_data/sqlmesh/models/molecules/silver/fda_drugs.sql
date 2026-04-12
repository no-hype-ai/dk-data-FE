-- SQLMesh Model: Silver FDA Drugs (NDA/ANDA/BLA approvals)
-- Promotes mol_bronze.fda_drugs to silver, linking to mol_silver.molecules.
-- Consolidated: previously split across fda_drugs and fda_drugsfda bronze models;
--   both sources are now merged in mol_bronze.fda_drugs.
-- Feature: 019-cms-puf-platform-reconciliation
--
-- Grain: application_number
-- Source: mol_bronze.fda_drugs (from mol_raw.fda_drugs via FDADrugsFetcher)

MODEL (
    name mol_silver.fda_drugs,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key application_number
    ),
    cron '@weekly',
    audits (
        not_null(columns := (application_number))
    ),
    grain application_number,
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

SELECT DISTINCT ON (b.application_number)
    b.application_number,
    b.application_type,
    b.sponsor_name,
    b.generic_name,
    b.brand_name,
    b.substance_name,
    b.rxcui,
    b.dosage_form,
    b.route,
    b.marketing_status,
    b.te_code,
    b.reference_drug,
    b.reference_standard,
    b.first_approval_date,
    b.products,
    b.submissions,
    b.app_num,
    b.approval_date_raw,
    m.molecule_id,
    b.source,
    b.source_updated_at,
    b.ingested_at,
    CURRENT_TIMESTAMP                   AS _silver_updated_at
FROM mol_bronze.fda_drugs AS b
LEFT JOIN mol_silver.molecules AS m
    ON LOWER(TRIM(b.generic_name)) = LOWER(TRIM(m.canonical_name))
WHERE b.application_number IS NOT NULL
ORDER BY b.application_number, b.source_updated_at DESC NULLS LAST
