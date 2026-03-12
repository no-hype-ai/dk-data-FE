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
    name silver.cms_facility_profile,
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
        SUM(total_discharges * avg_medicare_payments)
            / NULLIF(SUM(total_discharges), 0)  AS weighted_avg_medicare_payment,
        COUNT(DISTINCT drg_code)                AS distinct_drg_count
    FROM bronze.cms_inpatient_puf
    GROUP BY provider_id
),

outpatient_agg AS (
    SELECT
        provider_id                             AS ccn,
        SUM(total_services)                     AS total_outpatient_services,
        COUNT(DISTINCT apc_code)                AS distinct_apc_count
    FROM bronze.cms_outpatient_puf
    GROUP BY provider_id
),

affiliation_agg AS (
    SELECT
        ccn,
        COUNT(DISTINCT npi)                     AS affiliated_provider_count
    FROM bronze.cms_hospital_affiliation
    GROUP BY ccn
),

hcris_latest AS (
    SELECT DISTINCT ON (provider_ccn)
        provider_ccn                            AS ccn,
        total_costs,
        total_revenue,
        net_income,
        fiscal_year_begin,
        fiscal_year_end
    FROM bronze.cms_hcris
    WHERE provider_ccn IS NOT NULL
    ORDER BY provider_ccn, fiscal_year_end DESC
),

-- Bridge PECOS enrollment to facilities via hospital_affiliation
-- CCN (6-char facility ID) ≠ NPI (10-digit provider ID) — cannot be joined directly
-- hospital_affiliation provides the CCN→NPI crosswalk
pecos_via_affiliation AS (
    SELECT DISTINCT ON (ha.ccn)
        ha.ccn,
        pe.enrollment_type,
        pe.enrollment_state
    FROM bronze.cms_hospital_affiliation ha
    INNER JOIN (
        SELECT DISTINCT ON (npi)
            npi,
            enrollment_type,
            enrollment_state
        FROM bronze.cms_pecos
        ORDER BY npi, _loaded_at DESC
    ) pe ON ha.npi = pe.npi
    ORDER BY ha.ccn, pe.enrollment_type
),

magnet_status AS (
    SELECT
        facility_id,
        facility_name,
        state,
        designation_date,
        expiration_date,
        CASE
            WHEN expiration_date IS NULL OR expiration_date >= CURRENT_DATE
            THEN TRUE
            ELSE FALSE
        END                                     AS is_magnet
    FROM bronze.cms_magnet
)

SELECT
    pos.ccn,
    pos.facility_name,
    pos.facility_type,
    pos.address,
    pos.city,
    pos.state,
    pos.zip_code,

    -- Bed capacity
    pos.bed_count                                                               AS total_beds,

    -- Ownership from Hospital General Info (more detailed than POS)
    COALESCE(hgi.ownership, pos.facility_type)                                  AS ownership_type,
    hgi.hospital_type,

    -- Quality ratings
    hgi.overall_rating                                                          AS overall_quality_rating,

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

FROM bronze.cms_pos pos
LEFT JOIN bronze.cms_hospital_general_info hgi ON pos.ccn = hgi.provider_id
LEFT JOIN inpatient_agg inp ON pos.ccn = inp.ccn
LEFT JOIN outpatient_agg outp ON pos.ccn = outp.ccn
LEFT JOIN affiliation_agg aff ON pos.ccn = aff.ccn
LEFT JOIN hcris_latest hcris ON pos.ccn = hcris.ccn
LEFT JOIN pecos_via_affiliation pecos ON pos.ccn = pecos.ccn
LEFT JOIN magnet_status mag ON pos.ccn = mag.facility_id;
