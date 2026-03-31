-- SQLMesh Model: Silver Regulatory Milestones
-- FDA Drugs@FDA approval history from mol_bronze.fda_drugs with molecule_id linkage.
-- Previously sourced from both fda_drugsfda (targeted) + fda_drugs (bulk); merged into
-- mol_bronze.fda_drugs after audit confirmed mol_raw.fda_drugsfda was never populated
-- (no fetcher wrote to it — FDADrugsFetcher always wrote to mol_raw.fda_drugs).
-- Used by: assessment pipeline via PostgREST (path: /regulatory_milestones, schema: mol_silver).

MODEL (
    name mol_silver.regulatory_milestones,
    kind FULL,
    cron '@weekly',
    audits (
        not_null(columns := (application_number, source))
    ),
    grain application_number
);

WITH deduped AS (
    SELECT DISTINCT ON (application_number)
        b.application_number,
        b.sponsor_name,
        b.generic_name,
        b.brand_name,
        b.substance_name,
        b.rxcui,
        b.dosage_form,
        b.route,
        b.marketing_status,
        b.first_approval_date,
        b.products,
        b.submissions,
        'fda_drugs' AS source,
        b.source_updated_at
    FROM mol_bronze.fda_drugs b
    WHERE b.application_number IS NOT NULL
    ORDER BY application_number, b.source_updated_at DESC NULLS LAST
)

SELECT
    gen_random_uuid()                                   AS id,
    COALESCE(m_name.molecule_id, m_alias.molecule_id)  AS molecule_id,
    d.application_number,
    d.sponsor_name,
    d.generic_name,
    d.brand_name,
    d.substance_name,
    d.rxcui,
    d.dosage_form,
    d.route,
    d.marketing_status,
    d.first_approval_date,
    -- Derive application type from prefix
    CASE
        WHEN d.application_number ILIKE 'NDA%' THEN 'NDA'
        WHEN d.application_number ILIKE 'ANDA%' THEN 'ANDA'
        WHEN d.application_number ILIKE 'BLA%' THEN 'BLA'
        WHEN d.application_number ILIKE 'NDA%' THEN 'NDA'
        ELSE SPLIT_PART(d.application_number, ' ', 1)
    END                                                 AS application_type,
    d.products,
    d.submissions,
    d.source,
    d.source_updated_at,
    NOW()                                               AS created_at

FROM deduped d
-- Link via generic_name → canonical_name
LEFT JOIN mol_silver.molecules m_name
       ON d.generic_name IS NOT NULL
      AND LOWER(m_name.canonical_name) = LOWER(d.generic_name)
-- Fallback: via alias
LEFT JOIN mol_silver.molecule_aliases ma
       ON m_name.molecule_id IS NULL
      AND d.generic_name IS NOT NULL
      AND LOWER(REGEXP_REPLACE(d.generic_name, '[^a-zA-Z0-9]', '', 'g')) = ma.alias_name_normalized
LEFT JOIN mol_silver.molecules m_alias
       ON m_alias.molecule_id = ma.molecule_id;
