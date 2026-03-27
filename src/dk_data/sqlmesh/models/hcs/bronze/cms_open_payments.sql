-- SQLMesh Model: Bronze CMS Open Payments (Sunshine Act)
-- Typed pass-through from hcs_raw.cms_open_payments
-- Feature: 019-cms-puf-platform-reconciliation (T012)

MODEL (
    name hcs_bronze.cms_open_payments,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (_source_hash, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (physician_profile_id, _source_year))
    ),
    grain (_source_hash, _source_year)
);

SELECT
    id,
    covered_recipient_type,
    physician_profile_id,
    physician_first_name,
    physician_last_name,
    physician_specialty,
    applicable_manufacturer_or_gpo_name,
    total_amount_of_payment_usdollars,
    date_of_payment,
    nature_of_payment_or_transfer_of_value,
    recipient_city,
    recipient_state,
    recipient_zip_code,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_open_payments;
