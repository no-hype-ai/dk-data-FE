-- SQLMesh Model: Bronze CMS Chronic Conditions Among Medicare Beneficiaries
-- Typed pass-through from hcs_raw.cms_chronic_conditions
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_chronic_conditions,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (bene_geo_cd, bene_age_lvl, chronic_condition, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (bene_geo_cd, chronic_condition, _source_year))
    ),
    grain (bene_geo_cd, bene_age_lvl, chronic_condition, _source_year)
);

SELECT
    id,
    bene_geo_lvl,
    bene_geo_cd,
    bene_geo_desc,
    bene_age_lvl,
    chronic_condition,
    prevalence,
    total_medicare_payment,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_chronic_conditions;
