-- SQLMesh Model: Silver HCS Drug and Procedure Utilization
-- Cross-payer drug/HCPCS utilization — Medicare Part D + Part B + Medicaid + DME + Lab + Imaging.
-- Grain: (drug_or_hcpcs_code, code_type, _source_year)
--
-- molecule_id linkage (T116 rewrite — S3→LATERAL, molecule_aliases→molecule_names):
--   • Part D / Part B / Medicaid drug names → exact normalized name → first-token name (salt forms)
--   • HCPCS codes (DME/Lab/Imaging)         → mol_silver.hcpcs_molecule_bridge
--   NULL molecule_id = no match found; data is retained regardless.
--
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_silver.drug_utilization,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (drug_or_hcpcs_code, code_type, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (drug_or_hcpcs_code, code_type, _source_year))
    ),
    grain (drug_or_hcpcs_code, code_type, _source_year),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

-- Medicare Part D (drug spending by generic name)
WITH part_d AS (
    SELECT
        LOWER(TRIM(gnrc_name))              AS drug_or_hcpcs_code,
        'part_d_drug'                       AS code_type,
        brnd_name                           AS brand_name,
        NULL::TEXT                          AS manufacturer,
        _source_year,
        SUM(tot_clms)                       AS total_claims,
        SUM(tot_benes)                      AS total_beneficiaries,
        SUM(tot_spndng)                     AS total_cost,
        AVG(avg_spnd_per_clm)               AS avg_cost_per_claim,
        AVG(avg_spnd_per_bene)              AS avg_cost_per_beneficiary,
        NULL::NUMERIC                       AS medicaid_amount,
        NULL::INTEGER                       AS medicaid_prescriptions,
        NULL::INTEGER                       AS total_services,
        NULL::NUMERIC                       AS avg_medicare_allowed_amt,
        NULL::NUMERIC                       AS avg_medicare_payment_amt
    FROM hcs_bronze.cms_part_d_spending
    WHERE gnrc_name IS NOT NULL
    GROUP BY LOWER(TRIM(gnrc_name)), brnd_name, _source_year
),

-- Medicare Part B (drug spending by HCPCS code)
part_b AS (
    SELECT
        LOWER(TRIM(hcpcs_cd))               AS drug_or_hcpcs_code,
        'part_b_drug'                       AS code_type,
        hcpcs_desc                          AS brand_name,
        mftr_name                           AS manufacturer,
        _source_year,
        SUM(tot_clms)                       AS total_claims,
        SUM(tot_benes)                      AS total_beneficiaries,
        SUM(tot_spndng)                     AS total_cost,
        AVG(avg_spnd_per_clm)               AS avg_cost_per_claim,
        AVG(avg_spnd_per_bene)              AS avg_cost_per_beneficiary,
        NULL::NUMERIC                       AS medicaid_amount,
        NULL::INTEGER                       AS medicaid_prescriptions,
        SUM(tot_dsg_unts)                   AS total_services,
        AVG(avg_spnd_per_dsg_unt)           AS avg_medicare_allowed_amt,
        NULL::NUMERIC                       AS avg_medicare_payment_amt
    FROM hcs_bronze.cms_part_b_spending
    WHERE hcpcs_cd IS NOT NULL
    GROUP BY LOWER(TRIM(hcpcs_cd)), hcpcs_desc, mftr_name, _source_year
),

-- Medicaid drug spending (by generic drug name)
medicaid AS (
    SELECT
        LOWER(TRIM(gnrc_name))              AS drug_or_hcpcs_code,
        'medicaid_drug'                     AS code_type,
        brnd_name                           AS brand_name,
        NULL::TEXT                          AS manufacturer,
        _source_year,
        SUM(tot_prescriptions)              AS total_claims,
        SUM(tot_benes)                      AS total_beneficiaries,
        SUM(tot_spndng)                     AS total_cost,
        AVG(medicaid_spndng_per_prescription) AS avg_cost_per_claim,
        NULL::NUMERIC                       AS avg_cost_per_beneficiary,
        SUM(tot_spndng)                     AS medicaid_amount,
        SUM(tot_prescriptions)              AS medicaid_prescriptions,
        NULL::INTEGER                       AS total_services,
        NULL::NUMERIC                       AS avg_medicare_allowed_amt,
        NULL::NUMERIC                       AS avg_medicare_payment_amt
    FROM hcs_bronze.cms_medicaid_drug_spending
    WHERE gnrc_name IS NOT NULL
    GROUP BY LOWER(TRIM(gnrc_name)), brnd_name, _source_year
),

-- DME (by HCPCS code)
dme AS (
    SELECT
        LOWER(TRIM(hcpcs_cd))               AS drug_or_hcpcs_code,
        'dme_hcpcs'                         AS code_type,
        hcpcs_desc                          AS brand_name,
        NULL::TEXT                          AS manufacturer,
        _source_year,
        NULL::BIGINT                        AS total_claims,
        SUM(tot_suplr_benes)                AS total_beneficiaries,
        SUM(tot_suplr_clms * avg_suplr_mdcr_pymt_amt)  AS total_cost,
        NULL::NUMERIC                       AS avg_cost_per_claim,
        NULL::NUMERIC                       AS avg_cost_per_beneficiary,
        NULL::NUMERIC                       AS medicaid_amount,
        NULL::INTEGER                       AS medicaid_prescriptions,
        SUM(tot_suplr_srvcs)                AS total_services,
        AVG(avg_suplr_mdcr_alowd_amt)       AS avg_medicare_allowed_amt,
        AVG(avg_suplr_mdcr_pymt_amt)        AS avg_medicare_payment_amt
    FROM hcs_bronze.cms_dme_puf
    WHERE hcpcs_cd IS NOT NULL
    GROUP BY LOWER(TRIM(hcpcs_cd)), hcpcs_desc, _source_year
),

-- Lab services (by HCPCS code)
lab AS (
    SELECT
        LOWER(TRIM(hcpcs_cd))               AS drug_or_hcpcs_code,
        'lab_hcpcs'                         AS code_type,
        hcpcs_desc                          AS brand_name,
        NULL::TEXT                          AS manufacturer,
        _source_year,
        NULL::BIGINT                        AS total_claims,
        SUM(tot_benes)                      AS total_beneficiaries,
        SUM(tot_srvcs * avg_mdcr_pymt_amt)  AS total_cost,
        NULL::NUMERIC                       AS avg_cost_per_claim,
        NULL::NUMERIC                       AS avg_cost_per_beneficiary,
        NULL::NUMERIC                       AS medicaid_amount,
        NULL::INTEGER                       AS medicaid_prescriptions,
        SUM(tot_srvcs)                      AS total_services,
        AVG(avg_mdcr_alowd_amt)             AS avg_medicare_allowed_amt,
        AVG(avg_mdcr_pymt_amt)              AS avg_medicare_payment_amt
    FROM hcs_bronze.cms_lab_services
    WHERE hcpcs_cd IS NOT NULL
    GROUP BY LOWER(TRIM(hcpcs_cd)), hcpcs_desc, _source_year
),

-- Imaging (by HCPCS code)
imaging AS (
    SELECT
        LOWER(TRIM(hcpcs_cd))               AS drug_or_hcpcs_code,
        'imaging_hcpcs'                     AS code_type,
        hcpcs_desc                          AS brand_name,
        NULL::TEXT                          AS manufacturer,
        _source_year,
        NULL::BIGINT                        AS total_claims,
        SUM(tot_benes)                      AS total_beneficiaries,
        SUM(tot_srvcs * avg_mdcr_pymt_amt)  AS total_cost,
        NULL::NUMERIC                       AS avg_cost_per_claim,
        NULL::NUMERIC                       AS avg_cost_per_beneficiary,
        NULL::NUMERIC                       AS medicaid_amount,
        NULL::INTEGER                       AS medicaid_prescriptions,
        SUM(tot_srvcs)                      AS total_services,
        AVG(avg_mdcr_alowd_amt)             AS avg_medicare_allowed_amt,
        AVG(avg_mdcr_pymt_amt)              AS avg_medicare_payment_amt
    FROM hcs_bronze.cms_imaging_puf
    WHERE hcpcs_cd IS NOT NULL
    GROUP BY LOWER(TRIM(hcpcs_cd)), hcpcs_desc, _source_year
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
    FROM part_b
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
),

aggregated AS (
    SELECT
        drug_or_hcpcs_code,
        code_type,
        _source_year,
        MAX(brand_name)                     AS brand_name,
        MAX(manufacturer)                   AS manufacturer,
        SUM(total_claims)                   AS total_claims,
        SUM(total_beneficiaries)            AS total_beneficiaries,
        SUM(total_cost)                     AS total_cost,
        AVG(avg_cost_per_claim)             AS avg_cost_per_claim,
        AVG(avg_cost_per_beneficiary)       AS avg_cost_per_beneficiary,
        SUM(medicaid_amount)                AS medicaid_amount,
        SUM(medicaid_prescriptions)         AS medicaid_prescriptions,
        SUM(total_services)                 AS total_services,
        AVG(avg_medicare_allowed_amt)       AS avg_medicare_allowed_amt,
        AVG(avg_medicare_payment_amt)       AS avg_medicare_payment_amt
    FROM all_codes
    WHERE drug_or_hcpcs_code IS NOT NULL
      AND LENGTH(TRIM(drug_or_hcpcs_code)) > 0
    GROUP BY drug_or_hcpcs_code, code_type, _source_year
)

SELECT
    gen_random_uuid()                       AS id,
    a.drug_or_hcpcs_code,
    a.code_type,
    a.brand_name,
    a.manufacturer,
    a._source_year,
    a.total_claims,
    a.total_beneficiaries,
    a.total_cost,
    a.avg_cost_per_claim,
    a.avg_cost_per_beneficiary,
    a.medicaid_amount,
    a.medicaid_prescriptions,
    a.total_services,
    a.avg_medicare_allowed_amt,
    a.avg_medicare_payment_amt,
    -- molecule_id: tiered linking via LEFT JOIN LATERAL (replaces S3 CASE WHEN correlated subqueries)
    --   Drug name codes (Part D / Part B / Medicaid):
    --     Tier 1a: exact name match on full stripped drug name via molecule_names hub
    --     Tier 1b: first-token match (salt forms: "paclitaxel protein-bound" → "paclitaxel")
    --   HCPCS codes (DME, lab, imaging):
    --     Tier 2:  hcpcs_molecule_bridge by HCPCS code
    COALESCE(name_full.molecule_id, name_first.molecule_id, hcpcs_link.molecule_id) AS molecule_id,
    NOW()                                   AS source_updated_at,
    NOW()                                   AS created_at,
    NOW()                                   AS updated_at
FROM aggregated a

-- Tier 1a: exact name match via molecule_names hub
LEFT JOIN LATERAL (
    SELECT mn.molecule_id
    FROM mol_silver.molecule_names mn
    WHERE a.code_type IN ('part_d_drug', 'part_b_drug', 'medicaid_drug')
      AND mn.normalized_name = LOWER(REGEXP_REPLACE(a.drug_or_hcpcs_code, '[^a-zA-Z0-9]', '', 'g'))
    ORDER BY mn.molecule_id LIMIT 1
) name_full ON TRUE

-- Tier 1b: first-token match (salt forms: "paclitaxel protein-bound" → "paclitaxel")
LEFT JOIN LATERAL (
    SELECT mn.molecule_id
    FROM mol_silver.molecule_names mn
    WHERE a.code_type IN ('part_d_drug', 'part_b_drug', 'medicaid_drug')
      AND name_full.molecule_id IS NULL
      AND LENGTH(SPLIT_PART(a.drug_or_hcpcs_code, ' ', 1)) >= 4
      AND mn.normalized_name = LOWER(REGEXP_REPLACE(SPLIT_PART(a.drug_or_hcpcs_code, ' ', 1), '[^a-zA-Z0-9]', '', 'g'))
    ORDER BY mn.molecule_id LIMIT 1
) name_first ON TRUE

-- Tier 2: HCPCS bridge for DME/lab/imaging codes
LEFT JOIN LATERAL (
    SELECT hb.molecule_id
    FROM mol_silver.hcpcs_molecule_bridge hb
    WHERE a.code_type NOT IN ('part_d_drug', 'part_b_drug', 'medicaid_drug')
      AND LOWER(a.drug_or_hcpcs_code) = LOWER(hb.hcpcs_code)
    ORDER BY hb.confidence DESC LIMIT 1
) hcpcs_link ON TRUE;
