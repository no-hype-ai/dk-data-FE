-- SQLMesh Model: Silver Regulatory Milestones
-- Combines FDA Drugs@FDA approval history (fda_drugsfda + fda_drugs) into
-- mol_silver.regulatory_milestones with molecule_id linkage.
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

-- FDA Drugs@FDA (drug-specific lookups via xenon assessment trigger)
WITH from_fda_drugsfda AS (
    SELECT
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
        'fda_drugsfda' AS source,
        b.source_updated_at
    FROM mol_bronze.fda_drugsfda b
    WHERE b.application_number IS NOT NULL
),

-- FDA Drugs bulk feed (periodic batch ingestion)
from_fda_drugs AS (
    SELECT
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
),

combined AS (
    SELECT * FROM from_fda_drugsfda
    UNION ALL
    SELECT * FROM from_fda_drugs
),

-- Prefer fda_drugsfda (targeted) over fda_drugs (bulk) for same application_number
deduped AS (
    SELECT DISTINCT ON (application_number) *
    FROM combined
    ORDER BY application_number,
        CASE source WHEN 'fda_drugsfda' THEN 0 ELSE 1 END,
        source_updated_at DESC NULLS LAST
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
