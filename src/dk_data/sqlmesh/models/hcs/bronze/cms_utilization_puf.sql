-- SQLMesh Model: Bronze CMS Medicare Utilization PUF
-- Typed pass-through from hcs_raw.cms_utilization_puf
-- Raw CMS field names preserved: Bene_Geo_Cd → bene_geo_cd, Srvcs_Per_Bene → srvcs_per_bene, etc.
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_utilization_puf,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (bene_geo_cd, bene_age_lvl, bene_demo_lvl, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (bene_geo_cd, _source_year))
    ),
    grain (bene_geo_cd, bene_age_lvl, bene_demo_lvl, _source_year)
);

SELECT
    id,
    bene_geo_lvl::TEXT                          AS bene_geo_lvl,
    bene_geo_desc::TEXT                         AS bene_geo_desc,
    bene_geo_cd::TEXT                           AS bene_geo_cd,
    bene_age_lvl::TEXT                          AS bene_age_lvl,
    bene_demo_lvl::TEXT                         AS bene_demo_lvl,
    bene_demo_desc::TEXT                        AS bene_demo_desc,
    srvcs_per_bene::NUMERIC                     AS srvcs_per_bene,
    ip_cvrd_stays_per_1000_benes::NUMERIC       AS ip_cvrd_stays_per_1000_benes,
    avg_ip_los::NUMERIC                         AS avg_ip_los,
    er_visits_per_1000_benes::NUMERIC           AS er_visits_per_1000_benes,
    phy_visits_per_bene::NUMERIC                AS phy_visits_per_bene,
    tot_mdcr_pymt_pc::NUMERIC                   AS tot_mdcr_pymt_pc,
    _source_year::INTEGER,
    _source_hash::TEXT,
    _source_file::TEXT,
    _loaded_at,
    FALSE AS processed_to_silver,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_utilization_puf;
