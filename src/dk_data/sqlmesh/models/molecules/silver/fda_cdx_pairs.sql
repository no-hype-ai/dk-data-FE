-- SQLMesh Model: Silver FDA Companion Diagnostic (CDx) Pairs
-- Molecule crosswalk via normalized drug_generic_name JOIN to mol_silver.molecules.
-- Feature: 006-claims-engine-data-gaps (T035)

MODEL (
    name mol_silver.fda_cdx_pairs,
    kind FULL,
    cron '@weekly',
    audits (
        not_null(columns := (cdx_id))
    ),
    grain (cdx_id)
);

SELECT
    b.cdx_id,
    b.device_name,
    b.manufacturer,
    b.intended_use,
    b.drug_trade_name,
    b.drug_generic_name,
    b.approval_date,
    b.submission_type,
    b.source_url,
    -- Molecule crosswalk via drug_generic_name
    m.id                    AS molecule_id,
    b.source_updated_at,
    NOW()                   AS created_at
FROM mol_bronze.fda_cdx_pairs b
LEFT JOIN mol_silver.molecules m
    ON LOWER(TRIM(b.drug_generic_name)) = LOWER(TRIM(m.name));
