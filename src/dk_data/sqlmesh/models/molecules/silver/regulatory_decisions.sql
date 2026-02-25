-- SQLMesh Model: Silver Regulatory Decisions
-- Normalized regulatory decision data from EMA and HTA agencies
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name silver.regulatory_decisions,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (agency, drug_name, indication, decision_date)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (agency, drug_name, decision_date))
    ),
    grain (agency, drug_name, indication, decision_date)
);

WITH ema_decisions AS (
    SELECT
        'EMA' AS agency,
        drug_name,
        COALESCE(active_substance, drug_name) AS active_substance,
        indication,
        authorization_status AS decision,
        decision_date,
        therapeutic_area,
        NULL::TEXT AS recommendation_details,
        source,
        source_updated_at
    FROM bronze.ema
    WHERE processed_to_silver = FALSE
      AND drug_name IS NOT NULL
),

hta_decisions AS (
    SELECT
        agency,
        drug_name,
        drug_name AS active_substance,
        indication,
        decision,
        decision_date,
        therapeutic_area,
        recommendation AS recommendation_details,
        source,
        source_updated_at
    FROM bronze.hta_decisions
    WHERE processed_to_silver = FALSE
      AND drug_name IS NOT NULL
),

combined AS (
    SELECT * FROM ema_decisions
    UNION ALL
    SELECT * FROM hta_decisions
)

SELECT DISTINCT ON (agency, drug_name, indication, decision_date)
    gen_random_uuid() AS id,
    agency,
    drug_name,
    active_substance,
    indication,
    decision,
    decision_date,
    therapeutic_area,
    recommendation_details,
    source,
    source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM combined
ORDER BY agency, drug_name, indication, decision_date,
    CASE source
        WHEN 'ema' THEN 1
        WHEN 'hta_decisions' THEN 2
    END;
