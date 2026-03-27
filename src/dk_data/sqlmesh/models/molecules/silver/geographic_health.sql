-- SQLMesh Model: Silver Geographic Health Metrics
-- Aggregates CMS Medicare Geographic Variation PUF data into a state-level
-- and county-level health metrics layer for facility scoring and market analysis.
-- Source: bronze.cms_geographic_variation
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name silver.geographic_health,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (year, bene_geo_lvl, bene_geo_cd)
    ),
    cron '@yearly',
    audits (
        not_null(columns := (year, bene_geo_lvl, bene_geo_desc))
    ),
    grain (year, bene_geo_lvl, bene_geo_cd)
);

-- Use only the "All beneficiaries" demographic slice for the summary layer
-- to avoid double-counting across age/demo/MCC sub-groups.
WITH all_benes AS (
    SELECT
        year,
        bene_geo_lvl,
        bene_geo_desc,
        bene_geo_cd,
        tot_benes,
        ip_cvrd_stays_per_1000_benes,
        er_visits_per_1000_benes,
        readmsn_rate,
        acute_hosp_readmsn_rate,
        tot_mdcr_stdzd_pymt_pc,
        tot_mdcr_pymt_pc,
        tot_mdcr_alowd_amt_pc,
        ma_prtcptn_rate,
        source_updated_at
    FROM bronze.cms_geographic_variation
    WHERE
        -- "All beneficiaries" summary rows only
        (bene_age_lvl IS NULL OR bene_age_lvl = 'All')
        AND (bene_demo_lvl IS NULL OR bene_demo_lvl = 'All')
        AND (bene_mcc_lvl IS NULL OR bene_mcc_lvl = 'All')
        AND bene_geo_lvl IS NOT NULL
        AND processed_to_silver = FALSE
),

-- Deduplicate: keep most recently loaded row per geographic slice / year
deduped AS (
    SELECT DISTINCT ON (year, bene_geo_lvl, bene_geo_cd)
        *
    FROM all_benes
    ORDER BY year, bene_geo_lvl, bene_geo_cd, source_updated_at DESC NULLS LAST
)

SELECT
    gen_random_uuid()                           AS id,

    -- Geographic identifiers
    d.year::INTEGER                             AS year,
    d.bene_geo_lvl::TEXT                        AS geo_level,      -- National / State / County
    d.bene_geo_desc::TEXT                       AS geo_name,
    d.bene_geo_cd::TEXT                         AS geo_fips_cd,    -- FIPS code, TEXT (leading zeros)

    -- Beneficiary count
    d.tot_benes::INTEGER                        AS total_beneficiaries,

    -- Utilization metrics (NUMERIC)
    d.ip_cvrd_stays_per_1000_benes::NUMERIC     AS inpatient_stays_per_1000,
    d.er_visits_per_1000_benes::NUMERIC         AS er_visits_per_1000,
    d.readmsn_rate::NUMERIC                     AS readmission_rate,
    d.acute_hosp_readmsn_rate::NUMERIC          AS acute_readmission_rate,

    -- Spending (per-capita NUMERIC)
    d.tot_mdcr_stdzd_pymt_pc::NUMERIC           AS medicare_stdzd_pymt_per_capita,
    d.tot_mdcr_pymt_pc::NUMERIC                 AS medicare_pymt_per_capita,
    d.tot_mdcr_alowd_amt_pc::NUMERIC            AS medicare_allowed_per_capita,

    -- Medicare Advantage (NUMERIC)
    d.ma_prtcptn_rate::NUMERIC                  AS ma_participation_rate,

    -- Derived: spending per inpatient stay (NULL if either is NULL or zero)
    CASE
        WHEN d.ip_cvrd_stays_per_1000_benes > 0
            AND d.tot_benes > 0
        THEN (d.tot_mdcr_stdzd_pymt_pc * d.tot_benes)
             / NULLIF(d.ip_cvrd_stays_per_1000_benes * d.tot_benes / 1000.0, 0)
        ELSE NULL
    END::NUMERIC                                AS avg_stdzd_cost_per_ip_stay,

    -- Source tracking
    d.source_updated_at                         AS source_updated_at,
    NOW()                                       AS created_at,
    NOW()                                       AS updated_at

FROM deduped d;
