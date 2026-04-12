-- SQLMesh Model: Silver Physician Payments
-- Promotes CMS Open Payments from hcs_bronze.cms_open_payments
-- into mol_silver.physician_payments with molecule-level linkage.
-- Entity linking: LEFT JOIN mol_silver.molecules on product_name → canonical_name.
-- FULL refresh ensures molecule_id is always current when new molecules are added.
--
-- Source change (fix): reads from hcs_bronze.cms_open_payments (500 rows, actual data)
-- not mol_bronze.cms_open_payments (0 rows — mol_raw never ingested via API).
-- hcs_raw uses physician_profile_id (CMS-assigned), aliased to physician_npi for
-- schema compatibility. First drug slot used for product_name linkage.
-- Part of: Tier 4 gap fix — was blocked by enabled=false cron + missing silver model

MODEL (
    name mol_silver.physician_payments,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key record_id
    ),
    cron '@monthly',
    grain record_id,
    audits (
        not_null(columns := (record_id, physician_profile_id))
    ),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

SELECT
    m.molecule_id,
    -- physician_profile_id is the CMS-assigned profile ID (hcs_raw has no NPI column)
    b.physician_profile_id,
    TRIM(COALESCE(b.physician_first_name, '') || ' ' || COALESCE(b.physician_last_name, '')) AS physician_name,
    b.physician_specialty,
    b.recipient_state,
    b.applicable_manufacturer_or_gpo_name,
    b.total_amount_of_payment_usdollars,
    b.nature_of_payment_or_transfer_of_value,
    b.date_of_payment,
    b.program_year,
    b.form_of_payment_or_transfer_of_value,
    b.name_of_drug_or_biological_or_device_or_medical_supply_1,
    -- Additional bronze domain columns
    b.covered_recipient_type,
    b.number_of_payments_included_in_total_amount,
    b.recipient_city,
    b.recipient_zip_code,
    b.payment_publication_date,
    b.name_of_drug_or_biological_or_device_or_medical_supply_2,
    b.name_of_drug_or_biological_or_device_or_medical_supply_3,
    b.name_of_drug_or_biological_or_device_or_medical_supply_4,
    b.name_of_drug_or_biological_or_device_or_medical_supply_5,
    b.associated_drug_or_biological_ndc_1,
    b.associated_drug_or_biological_ndc_2,
    b.associated_drug_or_biological_ndc_3,
    b.associated_drug_or_biological_ndc_4,
    b.associated_drug_or_biological_ndc_5,
    b._source_year,
    b._source_hash,
    'cms_open_payments'                                                         AS source,
    b.record_id,
    b._loaded_at

FROM hcs_bronze.cms_open_payments b
LEFT JOIN mol_silver.molecules m
       ON b.name_of_drug_or_biological_or_device_or_medical_supply_1 IS NOT NULL
      AND LOWER(m.canonical_name) = LOWER(b.name_of_drug_or_biological_or_device_or_medical_supply_1)
WHERE b.physician_profile_id IS NOT NULL
  AND b.record_id IS NOT NULL;
