-- SQLMesh Model: Bronze CMS Chronic Conditions Among Medicare Beneficiaries
-- Typed pass-through from hcs_raw.cms_chronic_conditions
-- Raw CMS field names preserved: Bene_Geo_Cd → bene_geo_cd, Bene_Cond → bene_cond, etc.
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_chronic_conditions,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (bene_geo_cd, bene_age_lvl, bene_cond, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (bene_geo_cd, bene_cond, _source_year))
    ),
    grain (bene_geo_cd, bene_age_lvl, bene_cond, _source_year)
);

SELECT
    id,
    bene_geo_lvl::TEXT                      AS bene_geo_lvl,
    bene_geo_desc::TEXT                     AS bene_geo_desc,
    bene_geo_cd::TEXT                       AS bene_geo_cd,
    bene_age_lvl::TEXT                      AS bene_age_lvl,
    bene_demo_lvl::TEXT                     AS bene_demo_lvl,
    bene_demo_desc::TEXT                    AS bene_demo_desc,
    bene_cond::TEXT                         AS bene_cond,
    prvlnc::NUMERIC                         AS prvlnc,
    tot_mdcr_stdzd_pymt_pc::NUMERIC         AS tot_mdcr_stdzd_pymt_pc,
    tot_mdcr_pymt_pc::NUMERIC               AS tot_mdcr_pymt_pc,
    hosp_readmsn_rate::NUMERIC              AS hosp_readmsn_rate,
    ed_visits_per_1000_benes::NUMERIC       AS ed_visits_per_1000_benes,
    _source_year::INTEGER,
    _source_hash::TEXT,
    _source_file::TEXT,
    _loaded_at,
    FALSE AS processed_to_silver,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_chronic_conditions;
