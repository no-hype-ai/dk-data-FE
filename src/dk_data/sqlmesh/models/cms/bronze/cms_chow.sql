-- SQLMesh Model: Bronze CMS Change of Ownership (CHOW)
-- Normalizes raw CHOW data to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration (Phase 3 — Facility MVP)

MODEL (
    name hcs_bronze.cms_chow,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (ccn, effective_date))),
    grain (ccn, effective_date)
);

SELECT
    TRIM(chow_id)::TEXT                         AS chow_id,
    TRIM(ccn)::TEXT                             AS ccn,
    UPPER(TRIM(old_owner))                      AS old_owner,
    UPPER(TRIM(new_owner))                      AS new_owner,
    effective_date::DATE                        AS effective_date,
    _loaded_at,
    _source_file,
    _source_hash
FROM hcs_raw.cms_chow
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
