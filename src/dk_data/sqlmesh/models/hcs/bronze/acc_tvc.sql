-- SQLMesh Model: Bronze ACC/TVC Certification
-- Transforms raw ACC/TVC certification data to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name hcs_bronze.acc_tvc,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (facility_id)),
        unique_values(columns := (facility_id))
    ),
    grain facility_id
);

-- acc_tvc_certification is a legacy file source loaded manually via --file.
-- Until the file is loaded, return an empty result set with the correct schema.
SELECT
    gen_random_uuid()       AS id,
    NULL::TEXT              AS facility_id,
    NULL::TEXT              AS facility_name,
    NULL::TEXT              AS city,
    NULL::TEXT              AS state,
    NULL::TEXT              AS certification_type,
    NULL::TEXT              AS cert_date,
    NULL::JSONB             AS volumes,
    NULL::UUID              AS raw_source_id,
    'acc_tvc'               AS source,
    NOW()                   AS request_timestamp,
    NOW()                   AS source_updated_at,
    FALSE                   AS processed_to_silver,
    NOW()                   AS created_at
WHERE FALSE;  -- empty until acc_tvc file is loaded via: python -m dk_data.ingestion.main acc_tvc --file <path>
