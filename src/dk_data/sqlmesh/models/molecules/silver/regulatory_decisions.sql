-- SQLMesh Model: Silver Regulatory Decisions
-- Normalized regulatory decision data from EMA and HTA agencies
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name mol_silver.regulatory_decisions,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (agency, active_substance, indication, decision_id)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (agency, active_substance))
    ),
    grain (agency, active_substance, indication, decision_id)
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
        ingested_at AS source_updated_at,
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
        decision_date
    FROM mol_bronze.hta_decisions
    WHERE processed_to_silver = FALSE
      AND drug_name IS NOT NULL
),

combined AS (
    SELECT * FROM ema_decisions
    UNION ALL
    SELECT * FROM hta_decisions
)

SELECT DISTINCT ON (agency, COALESCE(drug_name, product_name), indication, COALESCE(decision_date, authorization_date))
    gen_random_uuid() AS id,
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
FROM combined
ORDER BY agency, COALESCE(drug_name, product_name), indication, COALESCE(decision_date, authorization_date),
    CASE source
        WHEN 'ema' THEN 1
        WHEN 'hta_decisions' THEN 2
    END;
