MODEL (
  name mol_silver.healthcare_facilities,
  kind INCREMENTAL_BY_UNIQUE_KEY (
    unique_key (provider_id, source)
  ),
  grain (provider_id, source),
  audits (not_null(columns := [provider_id, source])),
  description 'Healthcare facility master record combining CMS inpatient, hospital info, cost reports, ACC TVC, and HRSA shortage areas'
);

WITH cms_inpatient AS (
  SELECT
    provider_id::TEXT                          AS provider_id,
    provider_id::TEXT                          AS facility_name,
    NULL::TEXT                                 AS city,
    NULL::TEXT                                 AS state,
    'hospital'                                 AS facility_type,
    NULL::INT                                  AS bed_count,
    CAST(total_discharges AS INT)              AS total_discharges,
    'cms_inpatient'                            AS source,
    _loaded_at
  FROM hcs_bronze.cms_inpatient
),

cms_hospital_info AS (
  SELECT
    provider_id::TEXT                          AS provider_id,
    hospital_name                              AS facility_name,
    city,
    state,
    hospital_type                              AS facility_type,
    NULL::INT                                  AS bed_count,
    NULL::INT                                  AS total_discharges,
    'cms_hospital_info'                        AS source,
    _loaded_at
  FROM hcs_bronze.cms_hospital_info
),

cms_cost_reports AS (
  SELECT
    provider_id::TEXT                          AS provider_id,
    provider_id::TEXT                          AS facility_name,
    NULL::TEXT                                 AS city,
    NULL::TEXT                                 AS state,
    'hospital'                                 AS facility_type,
    CAST(bed_count AS INT)                     AS bed_count,
    NULL::INT                                  AS total_discharges,
    'cms_cost_reports'                         AS source,
    _loaded_at
  FROM hcs_bronze.cms_cost_reports
),

acc_tvc AS (
  SELECT
    facility_id::TEXT                          AS provider_id,
    facility_name,
    city,
    state,
    certification_type                         AS facility_type,
    NULL::INT                                  AS bed_count,
    NULL::INT                                  AS total_discharges,
    'acc_tvc'                                  AS source,
    _loaded_at
  FROM hcs_bronze.acc_tvc
),

hrsa AS (
  SELECT
    hpsa_id::TEXT                              AS provider_id,
    designation_type                           AS facility_name,
    county                                     AS city,
    state,
    'shortage_area'                            AS facility_type,
    NULL::INT                                  AS bed_count,
    NULL::INT                                  AS total_discharges,
    'hrsa'                                     AS source,
    _loaded_at
  FROM hcs_bronze.hrsa
),

combined AS (
  SELECT * FROM cms_inpatient
  UNION ALL
  SELECT * FROM cms_hospital_info
  UNION ALL
  SELECT * FROM cms_cost_reports
  UNION ALL
  SELECT * FROM acc_tvc
  UNION ALL
  SELECT * FROM hrsa
)

SELECT DISTINCT ON (provider_id, source)
  provider_id,
  facility_name,
  city,
  state,
  facility_type,
  bed_count,
  total_discharges,
  source,
  _loaded_at
FROM combined
ORDER BY provider_id, source, _loaded_at DESC
