-- SQLMesh Model: Bronze CMS RBCS Classification
-- Normalizes raw Restructured BETOS Classification System to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_rbcs,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (hcpcs_code))),
    grain (hcpcs_code)
);

SELECT
    TRIM(hcpcs_code)::TEXT                      AS hcpcs_code,
    TRIM(rbcs_id)::TEXT                         AS rbcs_id,
    UPPER(TRIM(rbcs_category))                  AS rbcs_category,
    UPPER(TRIM(rbcs_subcategory))               AS rbcs_subcategory,
    UPPER(TRIM(rbcs_family))                    AS rbcs_family,
    _loaded_at,
    _source_file,
    _source_hash
FROM hcs_raw.cms_rbcs
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
