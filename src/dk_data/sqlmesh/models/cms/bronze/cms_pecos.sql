-- SQLMesh Model: Bronze CMS PECOS
-- Normalizes raw PECOS provider enrollment data to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration (Phase 3 — Facility MVP)

MODEL (
    name bronze.cms_pecos,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (enrollment_id))),
    grain (enrollment_id)
);

SELECT
    TRIM(enrollment_id)::TEXT                   AS enrollment_id,
    TRIM(npi)::TEXT                             AS npi,
    UPPER(TRIM(org_name))                       AS org_name,
    UPPER(TRIM(enrollment_type))                AS enrollment_type,
    UPPER(TRIM(enrollment_state))               AS enrollment_state,
    _loaded_at,
    _source_file,
    _source_hash
FROM raw.cms_pecos
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
