-- SQLMesh Model: Bronze CMS Open Payments (mol namespace pass-through)
-- Reads from hcs_raw.cms_open_payments — the loader (sources/cms_open_payments.py)
-- writes to hcs_raw, not mol_raw. This model exposes a mol_bronze view of the same
-- data so mol-namespace downstream models can reference mol_bronze.cms_open_payments
-- without a cross-namespace raw dependency.
--
-- Source of truth: hcs_bronze.cms_open_payments (INCREMENTAL_BY_UNIQUE_KEY)
-- This FULL pass-through is intentionally simple — no JSONB expansion needed since
-- hcs_raw.cms_open_payments stores typed columns, not JSONB envelopes.
--
-- Fix (issue #186 M8): previously sourced from mol_raw.cms_open_payments (always empty;
-- the API loader never wrote to mol_raw). Changed to hcs_raw.cms_open_payments.

MODEL (
    name mol_bronze.cms_open_payments,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (record_id))
    ),
    grain record_id
);

SELECT
    id,
    record_id,
    covered_recipient_type,
    physician_profile_id,
    physician_first_name,
    physician_last_name,
    physician_specialty,
    applicable_manufacturer_or_gpo_name,
    total_amount_of_payment_usdollars::NUMERIC(18,2)    AS total_amount_of_payment_usdollars,
    date_of_payment::DATE                               AS date_of_payment,
    number_of_payments_included_in_total_amount::INTEGER AS number_of_payments_included_in_total_amount,
    form_of_payment_or_transfer_of_value,
    nature_of_payment_or_transfer_of_value,
    recipient_city,
    recipient_state,
    recipient_zip_code,
    program_year::INTEGER                               AS program_year,
    payment_publication_date::DATE                      AS payment_publication_date,
    name_of_drug_or_biological_or_device_or_medical_supply_1,
    name_of_drug_or_biological_or_device_or_medical_supply_2,
    name_of_drug_or_biological_or_device_or_medical_supply_3,
    name_of_drug_or_biological_or_device_or_medical_supply_4,
    name_of_drug_or_biological_or_device_or_medical_supply_5,
    associated_drug_or_biological_ndc_1,
    associated_drug_or_biological_ndc_2,
    associated_drug_or_biological_ndc_3,
    associated_drug_or_biological_ndc_4,
    associated_drug_or_biological_ndc_5,
    drug_name_1_normalized,
    drug_name_2_normalized,
    drug_name_3_normalized,
    drug_name_4_normalized,
    drug_name_5_normalized,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    'cms_open_payments'                                 AS source,
    _loaded_at                                          AS source_updated_at,
    FALSE                                               AS processed_to_silver,
    NOW()                                               AS created_at
FROM hcs_raw.cms_open_payments;
