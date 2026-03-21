-- SQLMesh Model: Bronze CMS NDC Directory
-- Normalizes raw National Drug Code Directory to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name bronze.cms_ndc,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (ndc))),
    grain (ndc)
);

SELECT
    TRIM(ndc)::TEXT                             AS ndc,
    UPPER(TRIM(proprietary_name))               AS proprietary_name,
    UPPER(TRIM(nonproprietary_name))            AS nonproprietary_name,
    UPPER(TRIM(labeler_name))                   AS labeler_name,
    UPPER(TRIM(dosage_form))                    AS dosage_form,
    UPPER(TRIM(route))                          AS route,
    UPPER(TRIM(product_type))                   AS product_type,
    _loaded_at,
    _source_file,
    _source_hash
FROM hcs_raw.cms_ndc
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
