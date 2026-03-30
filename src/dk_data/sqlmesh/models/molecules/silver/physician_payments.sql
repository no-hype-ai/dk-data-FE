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
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (source_record_id, physician_npi))
    )
);

SELECT
    gen_random_uuid()                                                           AS payment_id,
    m.molecule_id,
    -- physician_profile_id is the CMS-assigned profile ID (hcs_raw has no NPI column)
    b.physician_profile_id                                                      AS physician_npi,
    TRIM(COALESCE(b.physician_first_name, '') || ' ' || COALESCE(b.physician_last_name, '')) AS physician_name,
    b.physician_specialty,
    b.recipient_state                                                           AS physician_state,
    b.applicable_manufacturer_or_gpo_name                                      AS manufacturer_name,
    b.total_amount_of_payment_usdollars                                        AS payment_amount,
    b.nature_of_payment_or_transfer_of_value                                   AS payment_nature,
    b.date_of_payment                                                           AS payment_date,
    b.program_year                                                              AS payment_year,
    b.form_of_payment_or_transfer_of_value                                     AS payment_form,
    b.name_of_drug_or_biological_or_device_or_medical_supply_1                AS product_name,
    b.name_of_drug_or_biological_or_device_or_medical_supply_1                AS associated_drug,
    'cms_open_payments'                                                         AS source,
    b.record_id                                                                 AS source_record_id,
    b._loaded_at                                                                AS created_at

FROM hcs_bronze.cms_open_payments b
LEFT JOIN mol_silver.molecules m
       ON b.name_of_drug_or_biological_or_device_or_medical_supply_1 IS NOT NULL
      AND LOWER(m.canonical_name) = LOWER(b.name_of_drug_or_biological_or_device_or_medical_supply_1)
WHERE b.physician_profile_id IS NOT NULL
  AND b.record_id IS NOT NULL;
