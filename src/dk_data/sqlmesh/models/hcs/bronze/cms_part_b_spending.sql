-- SQLMesh Model: Bronze CMS Part B Drug Spending
-- Typed pass-through from hcs_raw.cms_part_b_spending
-- Feature: 019-cms-puf-platform-reconciliation (T012)
--
-- CMS source fields: HCPCS_Cd, HCPCS_Desc, Tot_Mftr, Mftr_Name, Tot_Spndng,
--   Tot_Dsg_Unts, Tot_Benes, Tot_Clms, Avg_Spnd_Per_Dsg_Unt, Avg_Spnd_Per_Clm,
--   Avg_Spnd_Per_Bene, Outlier_Flag

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
    hcpcs_cd::TEXT                          AS hcpcs_cd,
    hcpcs_desc::TEXT                        AS hcpcs_desc,
    tot_mftr::TEXT                          AS tot_mftr,
    mftr_name::TEXT                         AS mftr_name,
    tot_spndng::NUMERIC                     AS tot_spndng,
    tot_dsg_unts::NUMERIC                   AS tot_dsg_unts,
    tot_benes::INTEGER                      AS tot_benes,
    tot_clms::INTEGER                       AS tot_clms,
    avg_spnd_per_dsg_unt::NUMERIC           AS avg_spnd_per_dsg_unt,
    avg_spnd_per_clm::NUMERIC               AS avg_spnd_per_clm,
    avg_spnd_per_bene::NUMERIC              AS avg_spnd_per_bene,
    outlier_flag::TEXT                      AS outlier_flag,
    _source_year::INTEGER                   AS _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_part_b_spending;
