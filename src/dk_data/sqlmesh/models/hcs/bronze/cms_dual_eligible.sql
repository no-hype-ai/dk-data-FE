-- SQLMesh Model: Bronze CMS Dual Eligible Medicare-Medicaid Beneficiaries
-- Typed pass-through from hcs_raw.cms_dual_eligible
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_dual_eligible,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (state, bene_age_lvl, bene_race_cd, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (state, _source_year))
    ),
    grain (state, bene_age_lvl, bene_race_cd, _source_year)
);

SELECT
    id,
    state,
    bene_age_lvl,
    bene_race_cd,
    dual_benes,
    non_dual_benes,
    dual_pymt_pc,
    non_dual_pymt_pc,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_dual_eligible;
