-- SQLMesh Model: Bronze CMS Part D Drug Spending
-- Typed pass-through from hcs_raw.cms_part_d_spending
-- Feature: 019-cms-puf-platform-reconciliation (T012)
--
-- CMS source fields: Brnd_Name, Gnrc_Name, Tot_Mftr, Tot_Spndng, Tot_Dsg_Unts,
--   Tot_Clms, Tot_Benes, Avg_Spnd_Per_Dsg_Unt_Wghtd, Avg_Spnd_Per_Clm,
--   Avg_Spnd_Per_Bene, Outlier_Flag

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
    brnd_name::TEXT                         AS brnd_name,
    gnrc_name::TEXT                         AS gnrc_name,
    tot_mftr::TEXT                          AS tot_mftr,
    tot_spndng::NUMERIC                     AS tot_spndng,
    tot_dsg_unts::NUMERIC                   AS tot_dsg_unts,
    tot_clms::INTEGER                       AS tot_clms,
    tot_benes::INTEGER                      AS tot_benes,
    avg_spnd_per_dsg_unt_wghtd::NUMERIC     AS avg_spnd_per_dsg_unt_wghtd,
    avg_spnd_per_clm::NUMERIC               AS avg_spnd_per_clm,
    avg_spnd_per_bene::NUMERIC              AS avg_spnd_per_bene,
    outlier_flag::TEXT                      AS outlier_flag,
    _source_year::INTEGER                   AS _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    FALSE AS processed_to_silver,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_part_d_spending;
