-- SQLMesh Model: Silver FDA Drug Shortages
-- Molecule crosswalk via normalized generic_name JOIN to mol_silver.molecules.
-- Feature: 006-claims-engine-data-gaps (T033)

MODEL (
    name mol_silver.fda_drug_shortages,
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (shortage_id, generic_name))
    ),
    grain (shortage_id)
);

SELECT
    b.shortage_id,
    b.generic_name,
    b.brand_name,
    b.company,
    b.status,
    b.shortage_reason,
    b.shortage_start_date,
    b.shortage_end_date,
    b.affected_products,
    b.notes,
    -- Molecule crosswalk: join on normalized generic_name
    m.id                    AS molecule_id,
    b.source_updated_at,
    NOW()                   AS created_at
FROM mol_bronze.fda_drug_shortages b
LEFT JOIN mol_silver.molecules m
    ON LOWER(TRIM(b.generic_name)) = LOWER(TRIM(m.name));
