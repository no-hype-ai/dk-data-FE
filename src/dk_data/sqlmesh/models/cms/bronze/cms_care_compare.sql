-- SQLMesh Model: Bronze CMS Care Compare
-- Normalizes raw Care Compare physician data to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name bronze.cms_care_compare,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (npi))),
    grain (npi)
);

SELECT
    TRIM(npi)::TEXT                                     AS npi,
    TRIM(pac_id)::TEXT                                  AS pac_id,
    TRIM(professional_enrollment_id)::TEXT              AS professional_enrollment_id,
    UPPER(TRIM(first_name))                             AS first_name,
    UPPER(TRIM(last_name))                              AS last_name,
    UPPER(TRIM(credential))                             AS credential,
    UPPER(TRIM(medical_school))                         AS medical_school,
    graduation_year::INTEGER                            AS graduation_year,
    UPPER(TRIM(primary_specialty))                      AS primary_specialty,
    _loaded_at,
    _source_file,
    _source_hash
FROM hcs_raw.cms_care_compare_physicians
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
