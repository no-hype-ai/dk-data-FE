-- SQLMesh Model: Silver Regulatory Decisions
-- Normalized regulatory decision data from EMA and HTA agencies
-- Entity linking: LEFT JOIN mol_silver.molecules on canonical_name → active_substance (or inn).
-- FULL refresh ensures molecule_id is always current when new molecules are added.
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name mol_silver.regulatory_decisions,
    kind FULL,
    cron '@weekly',
    audits (
        not_null(columns := (agency, active_substance))
    )
);

WITH ema_decisions AS (
    SELECT
        'EMA' AS agency,
        product_name,
        active_substance,
        NULL::TEXT AS indication,
        authorization_status,
        authorization_date,
        therapeutic_area,
        NULL::TEXT AS recommendation,
        'ema' AS source,
        ingested_at AS source_updated_at,
        -- EMA-specific columns (all carried forward from bronze)
        product_number,
        inn,
        atc_code,
        marketing_authorization_holder,
        revision_date,
        medicine_type,
        pharmacotherapeutic_group,
        epar_url,
        summary_url,
        -- HTA-only columns (NULL for EMA)
        NULL::TEXT AS guidance_id,
        NULL::TEXT AS title,
        NULL::TEXT AS url,
        NULL::TEXT AS icer_value,
        NULL::TEXT AS decision_id,
        NULL::TEXT AS drug_name,
        NULL::TEXT AS decision,
        NULL::DATE AS decision_date
    FROM mol_bronze.ema
    WHERE processed_to_silver = FALSE
      AND product_name IS NOT NULL
),

hta_decisions AS (
    SELECT
        agency,
        NULL::TEXT AS product_name,
        drug_name AS active_substance,
        indication,
        NULL::TEXT AS authorization_status,
        NULL::DATE AS authorization_date,
        therapeutic_area,
        recommendation,
        'hta_decisions' AS source,
        source_updated_at,
        -- EMA-only columns (NULL for HTA)
        NULL::TEXT AS product_number,
        NULL::TEXT AS inn,
        NULL::TEXT AS atc_code,
        NULL::TEXT AS marketing_authorization_holder,
        NULL::DATE AS revision_date,
        NULL::TEXT AS medicine_type,
        NULL::TEXT AS pharmacotherapeutic_group,
        NULL::TEXT AS epar_url,
        NULL::TEXT AS summary_url,
        -- HTA-specific columns (all from bronze)
        guidance_id,
        title,
        url,
        icer_value,
        decision_id,
        drug_name,
        decision,
        decision_date::DATE AS decision_date
    FROM mol_bronze.hta_decisions
    WHERE processed_to_silver = FALSE
      AND drug_name IS NOT NULL
),

-- NICE Technology Appraisals (dedicated NICE API)
nice_hta_decisions AS (
    SELECT
        'NICE' AS agency,
        NULL::TEXT AS product_name,
        drug_name AS active_substance,
        NULL::TEXT AS indication,
        NULL::TEXT AS authorization_status,
        NULL::DATE AS authorization_date,
        NULL::TEXT AS therapeutic_area,
        recommendation,
        'nice_hta' AS source,
        source_updated_at,
        -- EMA-only columns (NULL for NICE)
        NULL::TEXT AS product_number,
        NULL::TEXT AS inn,
        NULL::TEXT AS atc_code,
        NULL::TEXT AS marketing_authorization_holder,
        NULL::DATE AS revision_date,
        NULL::TEXT AS medicine_type,
        NULL::TEXT AS pharmacotherapeutic_group,
        NULL::TEXT AS epar_url,
        NULL::TEXT AS summary_url,
        -- HTA-specific columns
        guidance_id,
        title,
        NULL::TEXT AS url,
        icer_value,
        guidance_id AS decision_id,
        drug_name,
        decision,
        published_date AS decision_date
    FROM mol_bronze.nice_hta
    WHERE processed_to_silver = FALSE
      AND drug_name IS NOT NULL
),

combined AS (
    SELECT * FROM ema_decisions
    UNION ALL
    SELECT * FROM hta_decisions
    UNION ALL
    SELECT * FROM nice_hta_decisions
)

SELECT DISTINCT ON (agency, COALESCE(drug_name, product_name), indication, COALESCE(decision_date, authorization_date))
    gen_random_uuid() AS id,
    -- Entity link: resolve molecule_id from active_substance name, falling back to inn.
    -- NULL when the substance is not yet in mol_silver.molecules.
    COALESCE(m_sub.molecule_id, m_inn.molecule_id) AS molecule_id,
    agency,
    product_name,
    active_substance,
    indication,
    authorization_status,
    authorization_date,
    therapeutic_area,
    recommendation,
    source,
    source_updated_at,
    -- EMA-specific columns
    product_number,
    inn,
    atc_code,
    marketing_authorization_holder,
    revision_date,
    medicine_type,
    pharmacotherapeutic_group,
    epar_url,
    summary_url,
    -- HTA-specific columns
    guidance_id,
    title,
    url,
    icer_value,
    decision_id,
    drug_name,
    decision,
    decision_date,
    NOW() AS created_at,
    NOW() AS updated_at
FROM combined c
LEFT JOIN mol_silver.molecules m_sub
       ON LOWER(m_sub.canonical_name) = LOWER(c.active_substance)
LEFT JOIN mol_silver.molecules m_inn
       ON m_sub.molecule_id IS NULL
      AND c.inn IS NOT NULL
      AND LOWER(m_inn.canonical_name) = LOWER(c.inn)
ORDER BY agency, COALESCE(drug_name, product_name), indication, COALESCE(decision_date, authorization_date),
    CASE source
        WHEN 'ema' THEN 1
        WHEN 'hta_decisions' THEN 2
        WHEN 'nice_hta' THEN 3
    END;
