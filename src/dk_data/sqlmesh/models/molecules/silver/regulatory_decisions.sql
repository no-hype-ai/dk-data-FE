-- SQLMesh Model: Silver Regulatory Decisions
-- Normalized regulatory decision data from EMA, HTA agencies, and FDA Orange Book
-- Part of: 015-assessment-dashboard-integration
--
-- Sources:
--   mol_bronze.ema          : EMA marketing authorizations (product_name, active_substance,
--                         authorization_status, authorization_date, therapeutic_area)
--   mol_bronze.hta_decisions: NICE/G-BA/HAS/PBAC decisions (drug_name, indication,
--                         decision_type, decision_date, summary)
--   mol_bronze.orange_book  : FDA NDA/ANDA approvals (ingredient, trade_name, approval_date)

MODEL (
    name mol_silver.regulatory_decisions,
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
        'EMA'::TEXT                                         AS agency,
        -- product_name is the branded/trade name; use active_substance as canonical drug name
        COALESCE(e.active_substance, e.product_name)::TEXT  AS drug_name,
        e.active_substance::TEXT                            AS active_substance,
        NULL::TEXT                                          AS indication,
        e.authorization_status::TEXT                        AS decision,
        e.authorization_date::DATE                          AS decision_date,
        e.therapeutic_area::TEXT                            AS therapeutic_area,
        NULL::TEXT                                          AS recommendation_details,
        e.source,
        e.source_updated_at
    FROM mol_bronze.ema e
    WHERE e.processed_to_silver = FALSE
      AND COALESCE(e.active_substance, e.product_name) IS NOT NULL
      AND e.authorization_date IS NOT NULL
),

hta_decisions AS (
    SELECT
        h.agency::TEXT                                      AS agency,
        h.drug_name::TEXT                                   AS drug_name,
        h.drug_name::TEXT                                   AS active_substance,
        h.indication::TEXT                                  AS indication,
        -- decision_type is the stored field (decision_type from HTABodiesFetcher)
        h.decision_type::TEXT                               AS decision,
        h.decision_date::DATE                               AS decision_date,
        NULL::TEXT                                          AS therapeutic_area,
        -- summary holds the human-readable recommendation text
        h.summary::TEXT                                     AS recommendation_details,
        h.source,
        h.source_updated_at
    FROM mol_bronze.hta_decisions h
    WHERE h.processed_to_silver = FALSE
      AND h.drug_name IS NOT NULL
      AND h.decision_date IS NOT NULL
),

orange_book_decisions AS (
    SELECT
        'FDA'::TEXT                                         AS agency,
        -- ingredient is the INN / active ingredient
        ob.ingredient::TEXT                                 AS drug_name,
        ob.ingredient::TEXT                                 AS active_substance,
        NULL::TEXT                                          AS indication,
        COALESCE(ob.drug_type, 'approval')::TEXT            AS decision,
        ob.approval_date::DATE                              AS decision_date,
        NULL::TEXT                                          AS therapeutic_area,
        ob.te_code::TEXT                                    AS recommendation_details,
        ob.source,
        ob.source_updated_at
    FROM mol_bronze.orange_book ob
    WHERE ob.processed_to_silver = FALSE
      AND ob.ingredient IS NOT NULL
      AND ob.approval_date IS NOT NULL
),

combined AS (
    SELECT * FROM ema_decisions
    UNION ALL
    SELECT * FROM hta_decisions
    UNION ALL
    SELECT * FROM orange_book_decisions
)

SELECT DISTINCT ON (agency, drug_name, indication, decision_date)
    gen_random_uuid()           AS id,
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
    NOW()                       AS created_at,
    NOW()                       AS updated_at
FROM combined
ORDER BY
    agency,
    drug_name,
    indication,
    decision_date,
    CASE source
        WHEN 'ema'           THEN 1
        WHEN 'orange_book'   THEN 2
        WHEN 'hta_decisions' THEN 3
        ELSE 4
    END;
