-- SQLMesh Model: Bronze CMS Medicare Enrollment Data
-- Typed pass-through from hcs_raw.cms_enrollment_puf
-- Raw CMS field names preserved: State_Cd → state_cd, County_Cd → county_cd, etc.
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_enrollment_puf,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (state_cd, county_cd, bene_demo_lvl, bene_age_lvl, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (state_cd, _source_year))
    ),
    grain (state_cd, county_cd, bene_demo_lvl, bene_age_lvl, _source_year)
);

SELECT
    id,
    state_cd::TEXT                          AS state_cd,
    county_cd::TEXT                         AS county_cd,
    county_desc::TEXT                       AS county_desc,
    bene_demo_lvl::TEXT                     AS bene_demo_lvl,
    bene_demo_desc::TEXT                    AS bene_demo_desc,
    bene_age_lvl::TEXT                      AS bene_age_lvl,
    tot_benes::INTEGER                      AS tot_benes,
    orgnl_mdcr_benes::INTEGER               AS orgnl_mdcr_benes,
    ma_benes::INTEGER                       AS ma_benes,
    esrd_benes::INTEGER                     AS esrd_benes,
    dsbl_benes::INTEGER                     AS dsbl_benes,
    _source_year::INTEGER,
    _source_hash::TEXT,
    _source_file::TEXT,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_enrollment_puf;
