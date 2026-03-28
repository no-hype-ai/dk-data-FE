-- SQLMesh Model: Silver HCS Facility Profile
-- CCN/provider_id-centric consolidated facility view.
-- Grain: (provider_id, _source_year) — one row per CMS-certified facility per year.
--
-- Entity linking key: CMS Certification Number (CCN) = provider_id
-- Source precedence: Hospital General Info (1) > Cost Reports (2) > Inpatient/Outpatient (3)
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_silver.facility_profile,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (provider_id, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (provider_id, _source_year))
    ),
    grain (provider_id, _source_year)
);

-- Source 1: Hospital General Info — identity + quality ratings
WITH hospital_info AS (
    SELECT
        facility_id                     AS provider_id,
        facility_name,
        address,
        city_town                       AS city,
        state,
        zip_code,
        county_parish                   AS county,
        telephone_number,
        hospital_type,
        hospital_ownership,
        emergency_services,
        hospital_overall_rating,
        _source_year
    FROM hcs_bronze.cms_hospital_general_info
    WHERE facility_id IS NOT NULL
),

-- Source 2: Cost Reports — financial performance
cost_reports AS (
    SELECT
        provider_id,
        hospital_name,
        city,
        state,
        zip_code,
        fiscal_year_begin,
        fiscal_year_end,
        total_beds,
        total_discharges,
        net_patient_revenue,
        total_operating_expenses,
        operating_margin,
        _source_year
    FROM hcs_bronze.cms_cost_reports_puf
    WHERE provider_id IS NOT NULL
),

-- Source 3: Inpatient PUF — DRG volume summary
inpatient_agg AS (
    SELECT
        provider_id,
        _source_year,
        SUM(total_discharges)           AS ip_total_discharges,
        AVG(average_covered_charges)    AS ip_avg_covered_charges,
        AVG(average_total_payments)     AS ip_avg_total_payments,
        AVG(average_medicare_payments)  AS ip_avg_medicare_payments,
        COUNT(DISTINCT drg_definition)  AS ip_drg_count
    FROM hcs_bronze.cms_inpatient_puf
    WHERE provider_id IS NOT NULL
    GROUP BY provider_id, _source_year
),

-- Source 4: Outpatient PUF — APC volume summary
outpatient_agg AS (
    SELECT
        provider_id,
        _source_year,
        SUM(total_services)                     AS op_total_services,
        AVG(average_estimated_submitted_charges) AS op_avg_submitted_charges,
        AVG(average_total_payments)             AS op_avg_total_payments,
        AVG(average_medicare_payments)          AS op_avg_medicare_payments,
        COUNT(DISTINCT apc)                     AS op_apc_count
    FROM hcs_bronze.cms_outpatient_puf
    WHERE provider_id IS NOT NULL
    GROUP BY provider_id, _source_year
),

-- Source 5: SNF PUF — Skilled Nursing Facility RUG-level utilization (aggregated per facility)
snf AS (
    SELECT
        provider_id,
        _source_year,
        SUM(tot_benes)                  AS snf_total_benes,
        SUM(tot_cvrd_days)              AS snf_total_cvrd_days,
        AVG(avg_cvrd_days)              AS snf_avg_cvrd_days,
        SUM(tot_mdcr_alowd_amt)         AS snf_total_alowd_amt,
        SUM(tot_mdcr_pymt_amt)          AS snf_medicare_payment,
        AVG(avg_mdcr_pymt_amt)          AS snf_avg_payment,
        COUNT(DISTINCT rug_cd)          AS snf_rug_count
    FROM hcs_bronze.cms_snf_puf
    WHERE provider_id IS NOT NULL
    GROUP BY provider_id, _source_year
),

-- Canonical provider_id set
all_providers AS (
    SELECT provider_id, _source_year FROM hospital_info
    UNION SELECT provider_id, _source_year FROM cost_reports
    UNION SELECT provider_id, _source_year FROM inpatient_agg
    UNION SELECT provider_id, _source_year FROM outpatient_agg
    UNION SELECT provider_id, _source_year FROM snf
)

SELECT
    gen_random_uuid()                   AS id,
    a.provider_id,
    a._source_year,
    -- Facility identity (prefer hospital general info)
    COALESCE(hi.facility_name, cr.hospital_name)    AS facility_name,
    COALESCE(hi.address, cr.city)                   AS address,
    COALESCE(hi.city, cr.city)                      AS city,
    COALESCE(hi.state, cr.state)                    AS state,
    COALESCE(hi.zip_code, cr.zip_code)              AS zip_code,
    hi.county,
    hi.telephone_number,
    hi.hospital_type,
    hi.hospital_ownership,
    hi.emergency_services,
    hi.hospital_overall_rating,
    -- Financial performance (from cost reports)
    cr.fiscal_year_begin,
    cr.fiscal_year_end,
    cr.total_beds,
    cr.total_discharges                             AS reported_total_discharges,
    cr.net_patient_revenue,
    cr.total_operating_expenses,
    cr.operating_margin,
    -- Inpatient utilization
    ip.ip_total_discharges,
    ip.ip_avg_covered_charges,
    ip.ip_avg_total_payments,
    ip.ip_avg_medicare_payments,
    ip.ip_drg_count,
    -- Outpatient utilization
    op.op_total_services,
    op.op_avg_submitted_charges,
    op.op_avg_total_payments,
    op.op_avg_medicare_payments,
    op.op_apc_count,
    -- SNF
    snf.snf_total_benes,
    snf.snf_total_cvrd_days,
    snf.snf_avg_cvrd_days,
    snf.snf_total_alowd_amt,
    snf.snf_medicare_payment,
    snf.snf_avg_payment,
    snf.snf_rug_count,
    -- Facility classification
    CASE
        WHEN hi.hospital_type IS NOT NULL THEN 'hospital'
        WHEN snf.provider_id IS NOT NULL  THEN 'snf'
        WHEN op.provider_id IS NOT NULL   THEN 'outpatient'
        ELSE 'other'
    END AS facility_type,
    -- Data completeness
    CASE
        WHEN hi.provider_id IS NOT NULL AND cr.provider_id IS NOT NULL THEN 1.0
        WHEN hi.provider_id IS NOT NULL OR cr.provider_id IS NOT NULL  THEN 0.8
        ELSE 0.5
    END AS data_completeness_score,
    ARRAY_REMOVE(ARRAY[
        CASE WHEN hi.provider_id IS NOT NULL   THEN 'hospital_general_info' END,
        CASE WHEN cr.provider_id IS NOT NULL   THEN 'cost_reports_puf' END,
        CASE WHEN ip.provider_id IS NOT NULL   THEN 'inpatient_puf' END,
        CASE WHEN op.provider_id IS NOT NULL   THEN 'outpatient_puf' END,
        CASE WHEN snf.provider_id IS NOT NULL  THEN 'snf_puf' END
    ], NULL)                            AS data_sources,
    NOW()                               AS created_at,
    NOW()                               AS updated_at
FROM all_providers a
LEFT JOIN hospital_info hi  ON a.provider_id = hi.provider_id AND a._source_year = hi._source_year
LEFT JOIN cost_reports cr   ON a.provider_id = cr.provider_id AND a._source_year = cr._source_year
LEFT JOIN inpatient_agg ip  ON a.provider_id = ip.provider_id AND a._source_year = ip._source_year
LEFT JOIN outpatient_agg op ON a.provider_id = op.provider_id AND a._source_year = op._source_year
LEFT JOIN snf               ON a.provider_id = snf.provider_id AND a._source_year = snf._source_year;
