-- SQLMesh Model: Bronze CMS Part D Drug Spending
-- Typed pass-through from hcs_raw.cms_part_d_spending
-- Feature: 019-cms-puf-platform-reconciliation (T012)

MODEL (
    name hcs_bronze.cms_part_d_spending,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (_source_hash, gnrc_name, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (gnrc_name, _source_year))
    ),
    grain (_source_hash, gnrc_name, _source_year)
);

SELECT
    id,
    brnd_name,
    gnrc_name,
    mftr_name,
    tot_mftr,
    tot_clms,
    tot_30day_fills,
    tot_drug_cst,
    tot_benes,
    avg_spnd_per_clm,
    avg_spnd_per_30day_fills,
    avg_spnd_per_bene,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_part_d_spending;
