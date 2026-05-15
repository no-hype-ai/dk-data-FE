"""TAVR hospital profile loader (data-researcher §4.1 AHD-like proxy).

Composes `hcs_gold.tavr_hospital_profile` from the existing CMS / HRSA /
Census / USDA silver tables already maintained by dk-data. The full join
SQL lives in this module so the cascade ownership rule (CMS-first:
ownership > enrollment > IRS 990 > website evidence) is auditable and
testable.

Red-flag gate enforcement:
  - system_filing_applied_to_facility — system-level IRS 990 rows MUST NOT
    populate facility-grain fields. The loader's join keys are CCN-grain
    only; system_parent is populated from CMS Hospital All Owners (CCN→
    parent map), not from a system-level row joined directly to the
    facility.

Schema: migration 240.
Spec: .dk/specs/008-tavr-hospital-profile-provisioning/spec.md
"""

import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "tavr_hospital_profile"

_DEFAULT_SOURCE_CLASS = "public_machine_readable"
_DEFAULT_COVERAGE_CLASS = "baseline_public"
_DEFAULT_USE_CLASS = "facility_identity_and_scale"
_DEFAULT_GRAIN = "facility"
_DEFAULT_CONFIDENCE = 0.70
_DEFAULT_CAVEAT = (
    "AHD-like public facility profile derived from CMS + HRSA + Census; "
    "not equivalent to AHD subscription data"
)

_BUILD_GOLD_SQL = """
INSERT INTO hcs_gold.tavr_hospital_profile (
  ccn, facility_name, address, county_fips, cbsa, hrr, hsa, zcta, ruca,
  ownership, system_parent, source_confidence,
  facility_scale_band, bed_count, inpatient_days,
  teaching_proxy, cardiac_surgery_signal, cath_lab_signal, tvt_signal,
  source_class, coverage_class, use_class, grain, as_of_date,
  source_id, confidence, caveat_text
)
SELECT
  hgi.ccn,
  hgi.facility_name,
  COALESCE(hgi.address, '') AS address,
  COALESCE(hgi.county_fips, '') AS county_fips,
  COALESCE(cbsa.cbsa, '') AS cbsa,
  COALESCE(hrr.hrr, '') AS hrr,
  COALESCE(hrr.hsa, '') AS hsa,
  COALESCE(hgi.zcta, '') AS zcta,
  COALESCE(ruca.ruca, '') AS ruca,
  COALESCE(own.ownership, enr.ownership, NULL) AS ownership,
  own.system_parent,
  jsonb_build_object(
    'ownership', CASE
      WHEN own.ownership IS NOT NULL THEN 'cms_hospital_all_owners'
      WHEN enr.ownership IS NOT NULL THEN 'cms_pecos_enrollment'
      ELSE NULL
    END,
    'system_parent', CASE
      WHEN own.system_parent IS NOT NULL THEN 'cms_hospital_all_owners'
      ELSE NULL
    END
  ) AS source_confidence,
  CASE
    WHEN hcris.bed_count >= 500 THEN 'large'
    WHEN hcris.bed_count >= 200 THEN 'mid'
    WHEN hcris.bed_count >  0   THEN 'small'
    ELSE NULL
  END AS facility_scale_band,
  hcris.bed_count,
  hcris.inpatient_days,
  COALESCE(hcris.teaching_program, false) AS teaching_proxy,
  COALESCE(hcris.has_cardiac_surgery, false) AS cardiac_surgery_signal,
  COALESCE(hcris.has_cath_lab, false) AS cath_lab_signal,
  false AS tvt_signal,
  %s AS source_class,
  %s AS coverage_class,
  %s AS use_class,
  %s AS grain,
  NOW() AS as_of_date,
  %s AS source_id,
  %s AS confidence,
  %s AS caveat_text
FROM hcs_silver.cms_hospital_general_info hgi
LEFT JOIN hcs_silver.cms_hcris      hcris ON hcris.ccn = hgi.ccn
LEFT JOIN hcs_silver.cms_hospital_all_owners own ON own.ccn = hgi.ccn
LEFT JOIN hcs_silver.cms_pecos      enr   ON enr.ccn = hgi.ccn
LEFT JOIN hcs_silver.census_cbsa    cbsa  ON cbsa.county_fips = hgi.county_fips
LEFT JOIN hcs_silver.hrsa_ahrf      hrr   ON hrr.county_fips  = hgi.county_fips
LEFT JOIN hcs_silver.usda_ruca      ruca  ON ruca.zcta         = hgi.zcta
WHERE hgi.is_ipps_active = true
ON CONFLICT (ccn) DO UPDATE SET
  facility_name           = EXCLUDED.facility_name,
  address                 = EXCLUDED.address,
  county_fips             = EXCLUDED.county_fips,
  cbsa                    = EXCLUDED.cbsa,
  hrr                     = EXCLUDED.hrr,
  hsa                     = EXCLUDED.hsa,
  zcta                    = EXCLUDED.zcta,
  ruca                    = EXCLUDED.ruca,
  ownership               = EXCLUDED.ownership,
  system_parent           = EXCLUDED.system_parent,
  source_confidence       = EXCLUDED.source_confidence,
  facility_scale_band     = EXCLUDED.facility_scale_band,
  bed_count               = EXCLUDED.bed_count,
  inpatient_days          = EXCLUDED.inpatient_days,
  teaching_proxy          = EXCLUDED.teaching_proxy,
  cardiac_surgery_signal  = EXCLUDED.cardiac_surgery_signal,
  cath_lab_signal         = EXCLUDED.cath_lab_signal,
  as_of_date              = NOW(),
  confidence              = EXCLUDED.confidence,
  caveat_text             = EXCLUDED.caveat_text,
  updated_at              = NOW()
"""

_COUNT_ROWS_SQL = "SELECT COUNT(*) FROM hcs_gold.tavr_hospital_profile"


def load_tavr_hospital_profile_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Refresh hcs_gold.tavr_hospital_profile from upstream silver tables.

    `records` is ignored; this loader is fully derived.
    """
    conn = get_connection()
    rows_written = 0
    total = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                _BUILD_GOLD_SQL,
                (
                    _DEFAULT_SOURCE_CLASS, _DEFAULT_COVERAGE_CLASS,
                    _DEFAULT_USE_CLASS, _DEFAULT_GRAIN,
                    SOURCE_ID, _DEFAULT_CONFIDENCE, _DEFAULT_CAVEAT,
                ),
            )
            rows_written = cur.rowcount or 0
            cur.execute(_COUNT_ROWS_SQL)
            total = cur.fetchone()[0]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    logger.info(
        "[%s] upserted=%d total_rows=%d", SOURCE_ID, rows_written, total,
    )
    return {
        "status": "success",
        "records_inserted": rows_written,
        "record_count": rows_written,
        "total_rows": total,
    }
