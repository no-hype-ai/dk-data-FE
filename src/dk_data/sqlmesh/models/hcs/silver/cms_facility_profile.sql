-- SQLMesh Model: Silver CMS Facility Profile
-- Joins bronze POS, PECOS, Hospital Quality, HCRIS, Hospital Affiliation,
-- Inpatient PUF, Outpatient PUF, Hospital General Info, and Magnet
-- into a unified facility profile with aggregated metrics
-- Part of: 016-cms-puf-datasource-integration (Phase 3 — Facility MVP)
--
-- Key design decisions:
-- 1. PECOS bridges through hospital_affiliation (CCN→NPI→PECOS) since
--    CCN and NPI are different identifier domains and cannot be joined directly
-- 2. HCRIS uses latest fiscal year per facility
-- 3. Magnet status derived from expiration_date

MODEL (
    name hcs_silver.cms_facility_profile,
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (ccn)),
        unique_values(columns := (ccn))
    ),
    grain (ccn)
);

WITH inpatient_agg AS (
    SELECT
        provider_id                             AS ccn,
        SUM(total_discharges)                   AS total_discharges,
        SUM(total_discharges * average_medicare_payments)
            / NULLIF(SUM(total_discharges), 0)  AS weighted_avg_medicare_payment,
        COUNT(DISTINCT drg_definition)          AS distinct_drg_count
    FROM hcs_bronze.cms_inpatient_puf
    GROUP BY provider_id
),

outpatient_agg AS (
    SELECT
        provider_id                             AS ccn,
        SUM(total_services)                     AS total_outpatient_services,
        COUNT(DISTINCT apc)                     AS distinct_apc_count
    FROM hcs_bronze.cms_outpatient_puf
    GROUP BY provider_id
),

affiliation_agg AS (
    SELECT
        -- facility_affiliations_certification_number is the CCN crosswalk field
        facility_affiliations_certification_number  AS ccn,
        COUNT(DISTINCT npi)                         AS affiliated_provider_count
    FROM hcs_bronze.cms_hospital_affiliation
    WHERE facility_affiliations_certification_number IS NOT NULL
    GROUP BY facility_affiliations_certification_number
),

hcris_by_year AS (
    -- Sum all worksheet line values per CCN per fiscal year.
    -- HCRIS G-worksheet totals: line_number '1' = total costs, '5' = net income (approximate).
    -- Aggregate all non-zero values as proxy total_reported_value; exact G-3 lines require
    -- worksheet-specific filters which vary by report type. The CCN + fiscal_year grain is stable.
    SELECT
        ccn,
        fiscal_year_begin,
        fiscal_year_end,
        SUM(CASE WHEN worksheet LIKE 'G%' AND value > 0 THEN value ELSE 0 END)  AS total_costs_proxy,
        SUM(CASE WHEN worksheet LIKE 'G%' AND value < 0 THEN ABS(value) ELSE 0 END) AS net_deficit_proxy,
        COUNT(*) AS line_count
    FROM hcs_bronze.cms_hcris
    WHERE ccn IS NOT NULL
    GROUP BY ccn, fiscal_year_begin, fiscal_year_end
),

hcris_latest AS (
    SELECT DISTINCT ON (ccn)
        ccn,
        fiscal_year_begin,
        fiscal_year_end,
        total_costs_proxy   AS total_costs,
        NULL::NUMERIC       AS total_revenue,   -- G-3 revenue lines require worksheet-specific logic
        NULL::NUMERIC       AS net_income       -- net income requires G-3 line 5 specifically
    FROM hcris_by_year
    ORDER BY ccn, fiscal_year_end DESC
),

-- Bridge PECOS enrollment to facilities via hospital_affiliation
-- CCN (6-char facility ID) ≠ NPI (10-digit provider ID) — cannot be joined directly
-- hospital_affiliation provides the CCN→NPI crosswalk via facility_affiliations_certification_number
pecos_via_affiliation AS (
    SELECT DISTINCT ON (ha.facility_affiliations_certification_number)
        ha.facility_affiliations_certification_number AS ccn,
        pe.enrollment_type,
        pe.enrollment_state
    FROM hcs_bronze.cms_hospital_affiliation ha
    INNER JOIN (
        SELECT DISTINCT ON (npi)
            npi,
            enrollment_type,
            enrollment_state
        FROM hcs_bronze.cms_pecos
        ORDER BY npi, ingested_at DESC
    ) pe ON ha.npi = pe.npi
    WHERE ha.facility_affiliations_certification_number IS NOT NULL
    ORDER BY ha.facility_affiliations_certification_number, pe.enrollment_type
),

magnet_status AS (
    SELECT
        facility_name,
        state,
        designation_date,
        -- cms_magnet only contains currently/recently designated facilities;
        -- presence in the register means active Magnet designation
        TRUE                                    AS is_magnet
    FROM hcs_bronze.cms_magnet
)

SELECT
    pos.ccn,
    pos.facility_name,
    pos.provider_type                                                           AS facility_type,
    pos.street_address                                                          AS address,
    pos.city,
    pos.state,
    pos.zip_code,

    -- Bed capacity
    pos.beds                                                                    AS total_beds,

    -- Ownership from Hospital General Info (more detailed than POS)
    COALESCE(hgi.hospital_ownership, pos.ownership_type)                        AS ownership_type,
    hgi.hospital_type,

    -- Hospital general info extended fields
    hgi.emergency_services,
    hgi.meets_criteria_for_birthing_friendly_designation,
    hgi.hospital_overall_rating_footnote,
    hgi.county_parish,
    hgi.telephone_number,

    -- Quality ratings (CMS Hospital Compare 5-star ratings via cms_hospital_quality)
    -- COALESCE: prefer dedicated quality bronze; fall back to hospital_general_info
    COALESCE(hq.overall_rating, hgi.hospital_overall_rating)                    AS overall_quality_rating,
    hq.mortality_rating,
    hq.safety_rating,
    hq.readmission_rating,
    hq.patient_experience_rating,
    hq.timeliness_rating,

    -- Inpatient metrics
    COALESCE(inp.total_discharges, 0)                                           AS total_discharges,
    COALESCE(inp.distinct_drg_count, 0)                                         AS distinct_drg_count,
    inp.weighted_avg_medicare_payment,

    -- Outpatient metrics
    COALESCE(outp.total_outpatient_services, 0)                                 AS total_outpatient_services,
    COALESCE(outp.distinct_apc_count, 0)                                        AS distinct_apc_count,

    -- Affiliation metrics
    COALESCE(aff.affiliated_provider_count, 0)                                  AS affiliated_provider_count,

    -- PECOS enrollment status (bridged via hospital_affiliation CCN→NPI→PECOS)
    pecos.enrollment_type                                                       AS enrollment_status,

    -- Financial metrics (HCRIS)
    hcris.total_costs,
    hcris.total_revenue,
    hcris.net_income,
    hcris.fiscal_year_begin                                                     AS hcris_fiscal_year_begin,
    hcris.fiscal_year_end                                                       AS hcris_fiscal_year_end,

    -- Magnet designation
    COALESCE(mag.is_magnet, FALSE)                                              AS magnet_status,
    mag.designation_date                                                        AS magnet_designation_date,

    NOW()                                                                       AS profile_built_at

FROM hcs_bronze.cms_pos pos
LEFT JOIN hcs_bronze.cms_hospital_general_info hgi ON pos.ccn = hgi.facility_id
LEFT JOIN hcs_bronze.cms_hospital_quality hq ON pos.ccn = hq.facility_id
LEFT JOIN inpatient_agg inp ON pos.ccn = inp.ccn
LEFT JOIN outpatient_agg outp ON pos.ccn = outp.ccn
LEFT JOIN affiliation_agg aff ON pos.ccn = aff.ccn
LEFT JOIN hcris_latest hcris ON pos.ccn = hcris.ccn
LEFT JOIN pecos_via_affiliation pecos ON pos.ccn = pecos.ccn
-- cms_magnet has no CCN; join on normalized name+state (best-effort)
LEFT JOIN magnet_status mag
    ON LOWER(pos.facility_name) = LOWER(mag.facility_name)
   AND pos.state = mag.state;
