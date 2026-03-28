-- SQLMesh Model: Bronze CMS Geographic Variation in Medicare Services
-- Typed pass-through from hcs_raw.cms_geographic_variation
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_geographic_variation,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (bene_geo_cd, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (bene_geo_cd, _source_year))
    ),
    grain (bene_geo_cd, _source_year)
);

SELECT
    id,
    bene_geo_lvl,
    bene_geo_cd,
    bene_geo_desc,
    year,
    tot_mdcr_stdzd_pymt_pc,
    tot_mdcr_pymt_pc,
    tot_mdcr_stdzd_pymt_pct_chg,
    hosp_readmsn_rate,
    er_visits_per_1000_benes,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    FALSE AS processed_to_silver,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_geographic_variation;
