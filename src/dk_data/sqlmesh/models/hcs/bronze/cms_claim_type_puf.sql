-- SQLMesh Model: Bronze CMS Medicare Claims by Type PUF
-- Typed pass-through from hcs_raw.cms_claim_type_puf
-- Raw CMS field names preserved: Clm_Type → clm_type, Tot_Clms → tot_clms, etc.
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_claim_type_puf,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (bene_geo_lvl, clm_type, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (_source_year))
    ),
    grain (bene_geo_lvl, clm_type, _source_year)
);

SELECT
    id,
    bene_geo_lvl::TEXT                      AS bene_geo_lvl,
    bene_geo_desc::TEXT                     AS bene_geo_desc,
    clm_type::TEXT                          AS clm_type,
    clm_type_desc::TEXT                     AS clm_type_desc,
    tot_clms::BIGINT                        AS tot_clms,
    tot_benes::INTEGER                      AS tot_benes,
    tot_mdcr_pymt_amt::NUMERIC              AS tot_mdcr_pymt_amt,
    avg_mdcr_pymt_amt::NUMERIC              AS avg_mdcr_pymt_amt,
    _source_year::INTEGER,
    _source_hash::TEXT,
    _source_file::TEXT,
    _loaded_at,
    FALSE AS processed_to_silver,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_claim_type_puf;
