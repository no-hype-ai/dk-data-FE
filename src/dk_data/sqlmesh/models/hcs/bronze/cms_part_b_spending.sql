-- SQLMesh Model: Bronze CMS Part B Drug Spending
-- Typed pass-through from hcs_raw.cms_part_b_spending
-- Feature: 019-cms-puf-platform-reconciliation (T012)

MODEL (
    name hcs_bronze.cms_part_b_spending,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (_source_hash, hcpcs_cd, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (hcpcs_cd, _source_year))
    ),
    grain (_source_hash, hcpcs_cd, _source_year)
);

SELECT
    id,
    hcpcs_cd,
    hcpcs_desc,
    provider_type,
    tot_allowed_amt,
    tot_mdcr_pymt_amt,
    tot_benes,
    tot_srvcs,
    avg_mdcr_pymt_amt,
    avg_submitted_chrg_amt,
    avg_allowed_amt,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_part_b_spending;
