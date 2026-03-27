-- SQLMesh Model: Bronze CMS Geographic Variation PUF
-- Transforms raw CMS Medicare Geographic Variation data to Bronze typed columns
-- Source: raw.cms_geographic_variation (flat typed table, loaded by cms_geographic_variation.py)
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name bronze.cms_geographic_variation,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (year, bene_geo_lvl, bene_geo_cd, bene_age_lvl, bene_demo_lvl, bene_demo_desc, bene_mcc_lvl)
    ),
    cron '@yearly',
    audits (
        not_null(columns := (year, bene_geo_lvl, bene_geo_desc))
    ),
    grain (year, bene_geo_lvl, bene_geo_cd, bene_age_lvl, bene_demo_lvl, bene_demo_desc, bene_mcc_lvl)
);

SELECT
    gen_random_uuid() AS id,

    -- Reference year (INTEGER)
    r.year::INTEGER AS year,

    -- Geographic identifiers (TEXT — FIPS codes have leading zeros)
    r.bene_geo_lvl::TEXT AS bene_geo_lvl,
    r.bene_geo_desc::TEXT AS bene_geo_desc,
    r.bene_geo_cd::TEXT AS bene_geo_cd,

    -- Beneficiary demographic slice (TEXT)
    r.bene_age_lvl::TEXT AS bene_age_lvl,
    r.bene_demo_lvl::TEXT AS bene_demo_lvl,
    r.bene_demo_desc::TEXT AS bene_demo_desc,
    r.bene_mcc_lvl::TEXT AS bene_mcc_lvl,

    -- Beneficiary counts (INTEGER)
    r.tot_benes::INTEGER AS tot_benes,

    -- Utilization rates (NUMERIC — rates per 1,000 or fractions)
    r.ip_cvrd_stays_per_1000_benes::NUMERIC AS ip_cvrd_stays_per_1000_benes,
    r.er_visits_per_1000_benes::NUMERIC AS er_visits_per_1000_benes,
    r.readmsn_rate::NUMERIC AS readmsn_rate,
    r.acute_hosp_readmsn_rate::NUMERIC AS acute_hosp_readmsn_rate,

    -- Spending per capita (NUMERIC)
    r.tot_mdcr_stdzd_pymt_pc::NUMERIC AS tot_mdcr_stdzd_pymt_pc,
    r.tot_mdcr_pymt_pc::NUMERIC AS tot_mdcr_pymt_pc,
    r.tot_mdcr_alowd_amt_pc::NUMERIC AS tot_mdcr_alowd_amt_pc,

    -- Medicare Advantage participation (NUMERIC — percentage 0-100)
    r.ma_prtcptn_rate::NUMERIC AS ma_prtcptn_rate,

    -- Source tracking
    r._source_hash AS source_hash,
    r._loaded_at AS source_updated_at,
    'cms_geographic_variation' AS source,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM raw.cms_geographic_variation r
WHERE
    r.bene_geo_lvl IS NOT NULL
    AND r.bene_geo_desc IS NOT NULL
    AND r._loaded_at BETWEEN @start_dt AND @end_dt;
