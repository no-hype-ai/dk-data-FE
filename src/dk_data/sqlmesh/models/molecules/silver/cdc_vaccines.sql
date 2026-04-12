-- SQLMesh Model: Silver CDC Vaccines
-- Promotes mol_bronze.cdc_vaccines into mol_silver.cdc_vaccines with molecule_id linkage.
-- Sources: CDC data.cdc.gov vaccine schedule rows + openFDA vaccine drug labels.
-- Entity linking: active_substance or generic_name → canonical_name/alias.

MODEL (
    name mol_silver.cdc_vaccines,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key vaccine_id
    ),
    cron '@monthly',
    audits (
        not_null(columns := (vaccine_id))
    ),
    grain vaccine_id,
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

SELECT
    gen_random_uuid()                                           AS id,
    COALESCE(m_sub.molecule_id, m_gen.molecule_id,
             m_alias.molecule_id)                              AS molecule_id,
    b.vaccine_id,
    b.vaccine_name,
    b.manufacturer,
    b.active_substance,
    b.generic_name,
    b.route,
    b.cvx_code,
    -- Normalise effective_date (openFDA format: YYYYMMDD or ISO)
    CASE
        WHEN b.effective_date ~ '^\d{8}$'
        THEN TO_DATE(b.effective_date, 'YYYYMMDD')
        WHEN b.effective_date ~ '^\d{4}-\d{2}-\d{2}'
        THEN TO_DATE(LEFT(b.effective_date, 10), 'YYYY-MM-DD')
        ELSE NULL
    END                                                         AS effective_date,
    -- Additional bronze domain columns
    b.record_type,
    b.full_vaccine_name,
    b.vaccine_status,
    b.notes,
    b.nonvaccine,
    b.update_date,
    b.mvx_status,
    'cdc_vaccines'                                              AS source,
    b.source_updated_at,
    NOW()                                                       AS created_at

FROM mol_bronze.cdc_vaccines b
-- Primary: active_substance → canonical_name
LEFT JOIN mol_silver.molecules m_sub
       ON b.active_substance IS NOT NULL
      AND LOWER(m_sub.canonical_name) = LOWER(b.active_substance)
-- Fallback: generic_name → canonical_name
LEFT JOIN mol_silver.molecules m_gen
       ON m_sub.molecule_id IS NULL
      AND b.generic_name IS NOT NULL
      AND LOWER(m_gen.canonical_name) = LOWER(b.generic_name)
-- Fallback: alias match on active_substance
LEFT JOIN mol_silver.molecule_names ma
       ON m_sub.molecule_id IS NULL
      AND m_gen.molecule_id IS NULL
      AND b.active_substance IS NOT NULL
      AND LOWER(REGEXP_REPLACE(b.active_substance, '[^a-zA-Z0-9]', '', 'g'))
          = ma.normalized_name
LEFT JOIN mol_silver.molecules m_alias
       ON m_alias.molecule_id = ma.molecule_id
WHERE b.vaccine_id IS NOT NULL;
