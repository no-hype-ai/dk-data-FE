-- SQLMesh Model: Bronze CMS Medicaid Drug Spending
-- Typed pass-through from hcs_raw.cms_medicaid_drug_spending
-- Feature: 019-cms-puf-platform-reconciliation
--
-- CMS source fields: Brnd_Name, Gnrc_Name, Tot_Mftr, Util_Type, Tot_Spndng,
--   Medicaid_Spndng_Per_Dosage_Unit, Medicaid_Spndng_Per_Prescription,
--   Unit_Type, Tot_Dosage_Units, Tot_Prescriptions, Tot_Benes

MODEL (
    name hcs_bronze.cms_medicaid_drug_spending,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (_source_hash, gnrc_name, util_type, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (_source_year))
    ),
    grain (_source_hash, gnrc_name, util_type, _source_year)
);

SELECT
    id,
    brnd_name::TEXT                                 AS brnd_name,
    gnrc_name::TEXT                                 AS gnrc_name,
    tot_mftr::TEXT                                  AS tot_mftr,
    util_type::TEXT                                 AS util_type,
    tot_spndng::NUMERIC                             AS tot_spndng,
    medicaid_spndng_per_dosage_unit::NUMERIC        AS medicaid_spndng_per_dosage_unit,
    medicaid_spndng_per_prescription::NUMERIC       AS medicaid_spndng_per_prescription,
    unit_type::TEXT                                 AS unit_type,
    tot_dosage_units::NUMERIC                       AS tot_dosage_units,
    tot_prescriptions::NUMERIC                      AS tot_prescriptions,
    tot_benes::NUMERIC                              AS tot_benes,
    _source_year::INTEGER                           AS _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    FALSE AS processed_to_silver,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_medicaid_drug_spending;
