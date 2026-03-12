-- SQLMesh Model: Bronze CMS Hospital Affiliation
-- Normalizes raw hospital affiliation data to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration (Phase 3 — Facility MVP)

MODEL (
    name bronze.cms_hospital_affiliation,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (ccn, affiliation_type))),
    grain (ccn, affiliation_type)
);

SELECT
    TRIM(affiliation_id)::TEXT                  AS affiliation_id,
    TRIM(npi)::TEXT                             AS npi,
    TRIM(ccn)::TEXT                             AS ccn,
    UPPER(TRIM(affiliation_type))               AS affiliation_type,
    _loaded_at,
    _source_file,
    _source_hash
FROM raw.cms_hospital_affiliation
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
