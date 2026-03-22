-- SQLMesh Model: Silver Physician Payments
-- Promotes CMS Open Payments from mol_bronze.cms_open_payments
-- into mol_silver.physician_payments with molecule-level linkage.
-- molecule_id is NULL here — entity linking fills it via product_name matching.
-- Part of: Tier 4 gap fix — was blocked by enabled=false cron + missing silver model

MODEL (
    name mol_silver.physician_payments,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (source_record_id)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (source_record_id, physician_npi))
    ),
    grain (source_record_id)
);

SELECT
    gen_random_uuid()                                           AS payment_id,
    NULL::UUID                                                  AS molecule_id,  -- entity linking fills this
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
WHERE b.processed_to_silver = FALSE
  AND b.physician_npi IS NOT NULL
  AND b.record_id IS NOT NULL;
