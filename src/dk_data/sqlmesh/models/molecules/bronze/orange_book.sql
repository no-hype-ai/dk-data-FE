-- SQLMesh Model: Bronze Orange Book
-- Transforms raw FDA Orange Book CSV data into typed bronze layer
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name bronze.orange_book,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        lookback 7
    ),
    cron '@weekly',
    grain (application_number, product_number, patent_number),
    audits (
        not_null(columns := (application_number))
    )
);

SELECT
    uuid_generate_v4() AS id,
    r.id AS raw_id,

    -- Drug identification
    COALESCE(
        r.response_body->>'Appl_No',
        r.response_body->>'application_number'
    ) AS application_number,
    COALESCE(
        r.response_body->>'Product_No',
        r.response_body->>'product_number',
        '001'
    ) AS product_number,
    COALESCE(
        r.response_body->>'Ingredient',
        r.response_body->>'ingredient'
    ) AS ingredient,
    COALESCE(
        r.response_body->>'Trade_Name',
        r.response_body->>'trade_name'
    ) AS trade_name,
    COALESCE(
        r.response_body->>'Applicant',
        r.response_body->>'applicant',
        r.response_body->>'Applicant_Full_Name'
    ) AS applicant,

    -- Drug details
    COALESCE(
        r.response_body->>'Strength',
        r.response_body->>'strength'
    ) AS strength,
    COALESCE(
        r.response_body->>'DF',
        r.response_body->>'Dosage_Form',
        r.response_body->>'dosage_form'
    ) AS dosage_form,
    COALESCE(
        r.response_body->>'Route',
        r.response_body->>'route'
    ) AS route,

    -- Approval info
    CASE
        WHEN r.response_body->>'Approval_Date' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (r.response_body->>'Approval_Date')::DATE
        WHEN r.response_body->>'approval_date' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (r.response_body->>'approval_date')::DATE
        ELSE NULL
    END AS approval_date,
    COALESCE(
        r.response_body->>'TE_Code',
        r.response_body->>'te_code'
    ) AS te_code,
    COALESCE(
        r.response_body->>'RLD',
        r.response_body->>'rld'
    ) AS rld,

    -- Patent info
    COALESCE(
        r.response_body->>'Patent_No',
        r.response_body->>'patent_number'
    ) AS patent_number,
    CASE
        WHEN r.response_body->>'Patent_Expire_Date_Text' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (r.response_body->>'Patent_Expire_Date_Text')::DATE
        WHEN r.response_body->>'patent_expiration' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (r.response_body->>'patent_expiration')::DATE
        ELSE NULL
    END AS patent_expiration,
    CASE
        WHEN r.response_body->>'Drug_Substance_Flag' = 'Y' THEN TRUE
        WHEN r.response_body->>'Drug_Substance_Flag' = 'N' THEN FALSE
        ELSE NULL
    END AS drug_substance_patent,
    CASE
        WHEN r.response_body->>'Drug_Product_Flag' = 'Y' THEN TRUE
        WHEN r.response_body->>'Drug_Product_Flag' = 'N' THEN FALSE
        ELSE NULL
    END AS drug_product_patent,
    COALESCE(
        r.response_body->>'Patent_Use_Code',
        r.response_body->>'patent_use_code'
    ) AS patent_use_code,

    -- Exclusivity info
    COALESCE(
        r.response_body->>'Exclusivity_Code',
        r.response_body->>'exclusivity_code'
    ) AS exclusivity_code,
    CASE
        WHEN r.response_body->>'Exclusivity_Date' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (r.response_body->>'Exclusivity_Date')::DATE
        WHEN r.response_body->>'exclusivity_date' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (r.response_body->>'exclusivity_date')::DATE
        ELSE NULL
    END AS exclusivity_date,

    -- Processing metadata
    FALSE AS processed_to_silver,
    NOW() AS ingested_at

FROM raw.orange_book r
WHERE r.response_status = 200
  AND r.processed_to_bronze = FALSE
  AND r.response_body IS NOT NULL
  AND COALESCE(
      r.response_body->>'Appl_No',
      r.response_body->>'application_number'
  ) IS NOT NULL
