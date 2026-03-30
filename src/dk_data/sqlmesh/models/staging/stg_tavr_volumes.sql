-- staging.tavr_volumes - TAVR procedure volumes by hospital
-- Source: hcs_raw.cms_medicare_inpatient filtered to TAVR DRGs
-- Model type: FULL refresh

MODEL (
    name staging.tavr_volumes,
    kind FULL,
    cron '@daily',
    description 'TAVR procedure volumes from CMS Medicare Inpatient data'
);

SELECT
    provider_id AS hospital_id,
    _source_year AS fiscal_year,
    drg_cd AS drg_code,
    total_discharges AS medicare_discharges,
    -- Estimate total volume: Medicare represents ~65% of TAVR procedures
    ROUND(total_discharges / 0.65)::INTEGER AS estimated_total_discharges,
    average_covered_charges AS average_charges,
    average_medicare_payments AS average_medicare_payment,
    NOW() AS _updated_at
FROM hcs_raw.cms_inpatient_puf
WHERE drg_cd IN ('266', '267')  -- TAVR DRG codes
  AND provider_id IS NOT NULL
  AND total_discharges > 0
  -- Deduplicate: take most recent load for each provider/year/drg
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY provider_id, _source_year, drg_cd
    ORDER BY _loaded_at DESC
) = 1;
