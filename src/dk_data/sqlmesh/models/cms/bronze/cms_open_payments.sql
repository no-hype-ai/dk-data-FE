-- SQLMesh Model: Bronze CMS Open Payments
-- Unions and normalizes all three Open Payments raw tables (general, research, ownership)
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name bronze.cms_open_payments,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (record_id))),
    grain (record_id)
);

SELECT
    TRIM(record_id)::TEXT                               AS record_id,
    TRIM(physician_npi)::TEXT                           AS physician_npi,
    UPPER(TRIM(payer_name))                             AS payer_name,
    total_amount_of_payment::NUMERIC(12,2)              AS total_amount_usd,
    UPPER(TRIM(nature_of_payment))                      AS payment_nature,
    UPPER(TRIM(form_of_payment))                        AS payment_form,
    'general'::TEXT                                     AS payment_type,
    program_year::INTEGER                               AS program_year,
    _loaded_at,
    _source_file,
    _source_hash
FROM raw.cms_open_payments_general
WHERE _loaded_at BETWEEN @start_dt AND @end_dt

UNION ALL

SELECT
    TRIM(record_id)::TEXT                               AS record_id,
    TRIM(physician_npi)::TEXT                           AS physician_npi,
    UPPER(TRIM(payer_name))                             AS payer_name,
    total_amount_of_payment::NUMERIC(12,2)              AS total_amount_usd,
    NULL::TEXT                                          AS payment_nature,
    UPPER(TRIM(form_of_payment))                        AS payment_form,
    'research'::TEXT                                    AS payment_type,
    program_year::INTEGER                               AS program_year,
    _loaded_at,
    _source_file,
    _source_hash
FROM raw.cms_open_payments_research
WHERE _loaded_at BETWEEN @start_dt AND @end_dt

UNION ALL

SELECT
    TRIM(record_id)::TEXT                               AS record_id,
    TRIM(physician_npi)::TEXT                           AS physician_npi,
    UPPER(TRIM(submitting_manufacturer))                AS payer_name,
    COALESCE(total_amount_invested, 0)::NUMERIC(12,2)   AS total_amount_usd,
    NULL::TEXT                                          AS payment_nature,
    NULL::TEXT                                          AS payment_form,
    'ownership'::TEXT                                   AS payment_type,
    program_year::INTEGER                               AS program_year,
    _loaded_at,
    _source_file,
    _source_hash
FROM raw.cms_open_payments_ownership
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
