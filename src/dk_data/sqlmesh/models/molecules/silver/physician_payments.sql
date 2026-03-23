-- SQLMesh Model: Silver Physician Payments
-- Promotes CMS Open Payments from mol_bronze.cms_open_payments
-- into mol_silver.physician_payments with molecule-level linkage.
-- Entity linking: LEFT JOIN mol_silver.molecules on product_name → canonical_name.
-- FULL refresh ensures molecule_id is always current when new molecules are added.
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
    gen_random_uuid()                                           AS payment_id,
    m.molecule_id,
    b.physician_npi,
    TRIM(b.physician_first_name || ' ' || b.physician_last_name) AS physician_name,
    b.physician_specialty,
    b.physician_state,
    b.manufacturer_name,
    b.payment_amount,
    b.payment_nature,
    b.payment_date,
    b.payment_year,
    b.payment_form,
    b.product_name                                              AS associated_drug,
    'cms_open_payments'                                         AS source,
    b.record_id                                                 AS source_record_id,
    b.ingested_at                                               AS created_at

FROM mol_bronze.cms_open_payments b
LEFT JOIN mol_silver.molecules m
       ON b.product_name IS NOT NULL
      AND LOWER(m.canonical_name) = LOWER(b.product_name)
WHERE b.physician_npi IS NOT NULL
  AND b.record_id IS NOT NULL;
