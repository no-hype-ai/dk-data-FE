-- SQLMesh Model: Bronze CMS Part D Prescribers by Provider and Drug
-- Typed pass-through from hcs_raw.cms_part_d_prescriber
-- Feature: 020-entity-linking-gaps
--
-- Grain: (prscrbr_npi, gnrc_name, _source_year)
-- No transformations — bronze is a schema-typed projection of raw.
-- Molecule linking happens in silver (hcs_silver.part_d_prescribing).
--
-- Column names match exact CMS PUF headers (snake_cased):
--   Prscrbr_NPI, Gnrc_Name, Tot_Clms, GE65_Sprsn_Flag, GE65_Bene_Sprsn_Flag, etc.

MODEL (
    name hcs_bronze.cms_part_d_prescriber,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (prscrbr_npi, gnrc_name, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (prscrbr_npi, gnrc_name, _source_year))
    ),
    grain (prscrbr_npi, gnrc_name, _source_year)
);

SELECT
    id,
    -- Provider identity
    prscrbr_npi,
    prscrbr_last_org_name,
    prscrbr_first_name,
    prscrbr_city,
    prscrbr_state_abrvtn,
    prscrbr_state_fips,
    prscrbr_type,
    prscrbr_type_src,
    -- Drug (generic name = molecule alias join key; brand name for context)
    brnd_name,
    gnrc_name,
    -- Utilization metrics (casts ensure consistent types even if raw stored as TEXT)
    tot_clms::BIGINT                AS tot_clms,
    tot_30day_fills::NUMERIC(18,2)  AS tot_30day_fills,
    tot_day_suply::BIGINT           AS tot_day_suply,
    tot_drug_cst::NUMERIC(18,2)     AS tot_drug_cst,
    tot_benes::INTEGER              AS tot_benes,
    -- 65+ sub-metrics with suppression flags
    ge65_sprsn_flag,
    ge65_tot_clms::BIGINT           AS ge65_tot_clms,
    ge65_tot_30day_fills::NUMERIC(18,2) AS ge65_tot_30day_fills,
    ge65_tot_drug_cst::NUMERIC(18,2)    AS ge65_tot_drug_cst,
    ge65_tot_day_suply::BIGINT      AS ge65_tot_day_suply,
    ge65_bene_sprsn_flag,
    ge65_tot_benes::INTEGER         AS ge65_tot_benes,
    -- Standard metadata
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_part_d_prescriber;
