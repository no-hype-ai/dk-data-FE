-- SQLMesh Model: Bronze CMS Hospital Quality
-- Normalizes raw Hospital Quality Measures data to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration (Phase 3 — Facility MVP)

MODEL (
    name hcs_bronze.cms_hospital_quality,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (provider_id, measure_id))),
    grain (provider_id, measure_id)
);

SELECT
    TRIM(provider_id)::TEXT                     AS provider_id,
    TRIM(measure_id)::TEXT                      AS measure_id,
    UPPER(TRIM(measure_name))                   AS measure_name,
    TRIM(score)::TEXT                           AS score,
    sample_size::INTEGER                        AS sample_size,
    TRIM(footnote)::TEXT                        AS footnote,
    _loaded_at,
    _source_file,
    _source_hash
FROM hcs_raw.cms_hospital_quality
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
