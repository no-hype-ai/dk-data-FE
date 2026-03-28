-- SQLMesh Model: Bronze CMS Dual Eligible Medicare-Medicaid Beneficiaries
-- Typed pass-through from hcs_raw.cms_dual_eligible
-- Raw CMS field names preserved: State_Cd → state_cd, Dual_Elgbl_Lvl → dual_elgbl_lvl, etc.
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_dual_eligible,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (state_cd, dual_elgbl_lvl, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (state_cd, _source_year))
    ),
    grain (state_cd, dual_elgbl_lvl, _source_year)
);

SELECT
    id,
    state_cd::TEXT                          AS state_cd,
    state_name::TEXT                        AS state_name,
    dual_elgbl_lvl::TEXT                    AS dual_elgbl_lvl,
    dual_elgbl_desc::TEXT                   AS dual_elgbl_desc,
    tot_benes::INTEGER                      AS tot_benes,
    ffs_benes::INTEGER                      AS ffs_benes,
    ma_benes::INTEGER                       AS ma_benes,
    dual_elgbl_full_benes::INTEGER          AS dual_elgbl_full_benes,
    dual_elgbl_prtl_benes::INTEGER          AS dual_elgbl_prtl_benes,
    non_dual_benes::INTEGER                 AS non_dual_benes,
    lis_benes::INTEGER                      AS lis_benes,
    _source_year::INTEGER,
    _source_hash::TEXT,
    _source_file::TEXT,
    _loaded_at,
    FALSE AS processed_to_silver,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_dual_eligible;
