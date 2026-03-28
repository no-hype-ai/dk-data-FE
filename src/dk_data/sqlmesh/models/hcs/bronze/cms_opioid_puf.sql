-- SQLMesh Model: Bronze CMS Opioid Prescribing Geographic Variation PUF
-- Typed pass-through from hcs_raw.cms_opioid_puf
-- Feature: 019-cms-puf-platform-reconciliation
--
-- Raw columns: prscrbr_npi (TEXT), prscrbr_last_org_name, prscrbr_first_name,
--   prscrbr_city, prscrbr_state_abrvtn, prscrbr_state_fips, prscrbr_type,
--   prscrbr_type_src, brnd_name, gnrc_name,
--   opioid_drug_flag (BOOLEAN), la_opioid_drug_flag (BOOLEAN),
--   tot_clms (INTEGER), tot_30day_fills (NUMERIC), tot_day_suply (INTEGER),
--   tot_drug_cst (NUMERIC), tot_benes (INTEGER),
--   opioid_clms (INTEGER), opioid_benes (INTEGER),
--   la_opioid_clms (INTEGER), la_opioid_benes (INTEGER)

MODEL (
    name hcs_bronze.cms_opioid_puf,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (prscrbr_npi, gnrc_name, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (prscrbr_npi, _source_year))
    ),
    grain (prscrbr_npi, gnrc_name, _source_year)
);

SELECT
    id::BIGINT,
    prscrbr_npi::TEXT,
    prscrbr_last_org_name::TEXT,
    prscrbr_first_name::TEXT,
    prscrbr_city::TEXT,
    prscrbr_state_abrvtn::TEXT,
    prscrbr_state_fips::TEXT,
    prscrbr_type::TEXT,
    prscrbr_type_src::TEXT,
    brnd_name::TEXT,
    gnrc_name::TEXT,
    opioid_drug_flag::BOOLEAN,
    la_opioid_drug_flag::BOOLEAN,
    tot_clms::INTEGER,
    tot_30day_fills::NUMERIC,
    tot_day_suply::INTEGER,
    tot_drug_cst::NUMERIC,
    tot_benes::INTEGER,
    opioid_clms::INTEGER,
    opioid_benes::INTEGER,
    la_opioid_clms::INTEGER,
    la_opioid_benes::INTEGER,
    _source_year::INTEGER,
    _source_hash::TEXT,
    _source_file::TEXT,
    _loaded_at::TIMESTAMPTZ,
    FALSE AS processed_to_silver,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_opioid_puf;
