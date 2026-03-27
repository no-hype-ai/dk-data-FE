-- SQLMesh Model: Silver HCS Drug and Procedure Utilization
-- Cross-payer drug/HCPCS utilization — Medicare Part D + Medicaid + DME + Lab + Imaging.
-- Grain: (drug_or_hcpcs_code, code_type, _source_year)
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_silver.drug_utilization,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (drug_or_hcpcs_code, code_type, _source_year))
    ),
    grain (drug_or_hcpcs_code, code_type, _source_year)
);

-- Medicare Part D (drug spending by generic name)
WITH part_d AS (
    SELECT
        LOWER(TRIM(gnrc_name))          AS drug_or_hcpcs_code,
        'part_d_drug'                   AS code_type,
        brnd_name                       AS brand_name,
        mftr_name                       AS manufacturer,
        _source_year,
        SUM(tot_clms)                   AS total_claims,
        SUM(tot_benes)                  AS total_beneficiaries,
        SUM(tot_drug_cst)               AS total_cost,
        AVG(avg_spnd_per_clm)           AS avg_cost_per_claim,
        AVG(avg_spnd_per_bene)          AS avg_cost_per_beneficiary,
        NULL::NUMERIC                   AS medicaid_amount,
        NULL::INTEGER                   AS medicaid_prescriptions,
        NULL::INTEGER                   AS total_services,
        NULL::NUMERIC                   AS avg_medicare_allowed_amt,
        NULL::NUMERIC                   AS avg_medicare_payment_amt
    FROM hcs_bronze.cms_part_d_spending
    WHERE gnrc_name IS NOT NULL
    GROUP BY LOWER(TRIM(gnrc_name)), brnd_name, mftr_name, _source_year
),

-- Medicaid drug spending (by generic drug name)
medicaid AS (
    SELECT
        LOWER(TRIM(drug_name))          AS drug_or_hcpcs_code,
        'medicaid_drug'                 AS code_type,
        NULL::TEXT                      AS brand_name,
        labeler_name                    AS manufacturer,
        _source_year,
        SUM(number_of_prescriptions)    AS total_claims,
        NULL::NUMERIC                   AS total_beneficiaries,
        SUM(total_amount_reimbursed)    AS total_cost,
        NULL::NUMERIC                   AS avg_cost_per_claim,
        NULL::NUMERIC                   AS avg_cost_per_beneficiary,
        SUM(medicaid_amount_reimbursed) AS medicaid_amount,
        SUM(number_of_prescriptions)    AS medicaid_prescriptions,
        NULL::INTEGER                   AS total_services,
        NULL::NUMERIC                   AS avg_medicare_allowed_amt,
        NULL::NUMERIC                   AS avg_medicare_payment_amt
    FROM hcs_bronze.cms_medicaid_drug_spending
    WHERE drug_name IS NOT NULL
    GROUP BY LOWER(TRIM(drug_name)), labeler_name, _source_year
),

-- DME (by HCPCS code)
dme AS (
    SELECT
        LOWER(TRIM(hcpcs_cd))           AS drug_or_hcpcs_code,
        'dme_hcpcs'                     AS code_type,
        hcpcs_desc                      AS brand_name,
        NULL::TEXT                      AS manufacturer,
        _source_year,
        NULL::BIGINT                    AS total_claims,
        SUM(total_unique_benes)         AS total_beneficiaries,
        SUM(total_medicare_payment_amt) AS total_cost,
        NULL::NUMERIC                   AS avg_cost_per_claim,
        NULL::NUMERIC                   AS avg_cost_per_beneficiary,
        NULL::NUMERIC                   AS medicaid_amount,
        NULL::INTEGER                   AS medicaid_prescriptions,
        SUM(total_unique_benes)         AS total_services,
        AVG(total_medicare_allowed_amt) AS avg_medicare_allowed_amt,
        AVG(total_medicare_payment_amt) AS avg_medicare_payment_amt
    FROM hcs_bronze.cms_dme_puf
    WHERE hcpcs_cd IS NOT NULL
    GROUP BY LOWER(TRIM(hcpcs_cd)), hcpcs_desc, _source_year
),

-- Lab services (by HCPCS code)
lab AS (
    SELECT
        LOWER(TRIM(hcpcs_cd))           AS drug_or_hcpcs_code,
        'lab_hcpcs'                     AS code_type,
        hcpcs_desc                      AS brand_name,
        NULL::TEXT                      AS manufacturer,
        _source_year,
        NULL::BIGINT                    AS total_claims,
        SUM(total_unique_benes)         AS total_beneficiaries,
        SUM(total_services * average_medicare_payment_amt) AS total_cost,
        NULL::NUMERIC                   AS avg_cost_per_claim,
        NULL::NUMERIC                   AS avg_cost_per_beneficiary,
        NULL::NUMERIC                   AS medicaid_amount,
        NULL::INTEGER                   AS medicaid_prescriptions,
        SUM(total_services)             AS total_services,
        AVG(average_medicare_allowed_amt) AS avg_medicare_allowed_amt,
        AVG(average_medicare_payment_amt) AS avg_medicare_payment_amt
    FROM hcs_bronze.cms_lab_services
    WHERE hcpcs_cd IS NOT NULL
    GROUP BY LOWER(TRIM(hcpcs_cd)), hcpcs_desc, _source_year
),

-- Imaging (by HCPCS code)
imaging AS (
    SELECT
        LOWER(TRIM(hcpcs_cd))           AS drug_or_hcpcs_code,
        'imaging_hcpcs'                 AS code_type,
        COALESCE(modality || ' - ', '') || hcpcs_desc AS brand_name,
        NULL::TEXT                      AS manufacturer,
        _source_year,
        NULL::BIGINT                    AS total_claims,
        SUM(total_unique_benes)         AS total_beneficiaries,
        SUM(total_services * average_medicare_payment_amt) AS total_cost,
        NULL::NUMERIC                   AS avg_cost_per_claim,
        NULL::NUMERIC                   AS avg_cost_per_beneficiary,
        NULL::NUMERIC                   AS medicaid_amount,
        NULL::INTEGER                   AS medicaid_prescriptions,
        SUM(total_services)             AS total_services,
        AVG(average_medicare_allowed_amt) AS avg_medicare_allowed_amt,
        AVG(average_medicare_payment_amt) AS avg_medicare_payment_amt
    FROM hcs_bronze.cms_imaging_puf
    WHERE hcpcs_cd IS NOT NULL
    GROUP BY LOWER(TRIM(hcpcs_cd)), modality, hcpcs_desc, _source_year
),

all_codes AS (
    SELECT drug_or_hcpcs_code, code_type, brand_name, manufacturer, _source_year,
           total_claims, total_beneficiaries, total_cost, avg_cost_per_claim,
           avg_cost_per_beneficiary, medicaid_amount, medicaid_prescriptions,
           total_services, avg_medicare_allowed_amt, avg_medicare_payment_amt
    FROM part_d
    UNION ALL SELECT drug_or_hcpcs_code, code_type, brand_name, manufacturer, _source_year,
           total_claims, total_beneficiaries, total_cost, avg_cost_per_claim,
           avg_cost_per_beneficiary, medicaid_amount, medicaid_prescriptions,
           total_services, avg_medicare_allowed_amt, avg_medicare_payment_amt
    FROM medicaid
    UNION ALL SELECT drug_or_hcpcs_code, code_type, brand_name, manufacturer, _source_year,
           total_claims, total_beneficiaries, total_cost, avg_cost_per_claim,
           avg_cost_per_beneficiary, medicaid_amount, medicaid_prescriptions,
           total_services, avg_medicare_allowed_amt, avg_medicare_payment_amt
    FROM dme
    UNION ALL SELECT drug_or_hcpcs_code, code_type, brand_name, manufacturer, _source_year,
           total_claims, total_beneficiaries, total_cost, avg_cost_per_claim,
           avg_cost_per_beneficiary, medicaid_amount, medicaid_prescriptions,
           total_services, avg_medicare_allowed_amt, avg_medicare_payment_amt
    FROM lab
    UNION ALL SELECT drug_or_hcpcs_code, code_type, brand_name, manufacturer, _source_year,
           total_claims, total_beneficiaries, total_cost, avg_cost_per_claim,
           avg_cost_per_beneficiary, medicaid_amount, medicaid_prescriptions,
           total_services, avg_medicare_allowed_amt, avg_medicare_payment_amt
    FROM imaging
)

SELECT
    gen_random_uuid()               AS id,
    drug_or_hcpcs_code,
    code_type,
    MAX(brand_name)                 AS brand_name,
    MAX(manufacturer)               AS manufacturer,
    _source_year,
    SUM(total_claims)               AS total_claims,
    SUM(total_beneficiaries)        AS total_beneficiaries,
    SUM(total_cost)                 AS total_cost,
    AVG(avg_cost_per_claim)         AS avg_cost_per_claim,
    AVG(avg_cost_per_beneficiary)   AS avg_cost_per_beneficiary,
    SUM(medicaid_amount)            AS medicaid_amount,
    SUM(medicaid_prescriptions)     AS medicaid_prescriptions,
    SUM(total_services)             AS total_services,
    AVG(avg_medicare_allowed_amt)   AS avg_medicare_allowed_amt,
    AVG(avg_medicare_payment_amt)   AS avg_medicare_payment_amt,
    NOW()                           AS created_at,
    NOW()                           AS updated_at
FROM all_codes
WHERE drug_or_hcpcs_code IS NOT NULL
  AND LENGTH(TRIM(drug_or_hcpcs_code)) > 0
GROUP BY drug_or_hcpcs_code, code_type, _source_year;
