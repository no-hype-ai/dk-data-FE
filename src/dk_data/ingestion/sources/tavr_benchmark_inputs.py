"""TAVR benchmark inputs loader — Phase 1B read-optimized scoring inputs.

Composes `hcs_gold.tavr_benchmark_inputs` by joining the Phase 1A outputs
(tavr_hospital_profile + tavr_program_year) with CMS Hospital Service Area
catchment + MSPB / VBP / HRRP / HAC payment-adjustment silver layers.

Red-flag gates enforced:
  - missing_denominator_or_year_or_grain_mismatch — grain CHECK + (ccn, year)
    PK + as_of_date NOW().
  - top_referrer_inferred_from_proximity — catchment_top_zips JSONB carries
    only CMS Hospital Service Area catchment shares (population-routed),
    NEVER inferred referrers. The column's COMMENT and the table COMMENT
    encode this constraint so future schema migrations cannot add a
    referrer column without licensed evidence.

Source lineage: every field's upstream gold/silver table name is recorded
in `source_lineage` JSONB per the handoff DoD ("every input field
references the upstream gold table that produced it").

Schema: migration 242.
Spec: .dk/specs/010-tavr-benchmark-inputs-provisioning/spec.md
"""

import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "tavr_benchmark_inputs"

_DEFAULT_SOURCE_CLASS = "public_machine_readable"
_DEFAULT_COVERAGE_CLASS = "baseline_public"
_DEFAULT_USE_CLASS = "scoring_inputs"
_DEFAULT_GRAIN = "hospital_year"
_DEFAULT_CONFIDENCE = 0.70
_DEFAULT_CAVEAT = (
    "Denormalized scoring inputs. Source lineage in source_lineage JSONB. "
    "Top-N ZIPs are CMS Hospital Service Area catchment shares, NOT "
    "inferred referrers."
)

# Static lineage map — every field references the upstream gold/silver
# table that produced it. Loader writes the same map for every row.
_SOURCE_LINEAGE = {
    "facility_name":           "hcs_gold.tavr_hospital_profile",
    "cbsa":                    "hcs_gold.tavr_hospital_profile",
    "hrr":                     "hcs_gold.tavr_hospital_profile",
    "facility_scale_band":     "hcs_gold.tavr_hospital_profile",
    "bed_count":               "hcs_gold.tavr_hospital_profile",
    "ownership":               "hcs_gold.tavr_hospital_profile",
    "system_parent":           "hcs_gold.tavr_hospital_profile",
    "teaching_proxy":          "hcs_gold.tavr_hospital_profile",
    "cardiac_surgery_signal":  "hcs_gold.tavr_hospital_profile",
    "cath_lab_signal":         "hcs_gold.tavr_hospital_profile",
    "drg_266_discharges":      "hcs_gold.tavr_program_year",
    "drg_267_discharges":      "hcs_gold.tavr_program_year",
    "avg_payment":             "hcs_gold.tavr_program_year",
    "avg_charge":              "hcs_gold.tavr_program_year",
    "mcc_capture_proxy":       "hcs_gold.tavr_program_year",
    "yoy_growth":              "hcs_gold.tavr_program_year",
    "national_percentile":     "hcs_gold.tavr_program_year",
    "state_percentile":        "hcs_gold.tavr_program_year",
    "catchment_top_zips":      "hcs_silver.cms_hospital_service_area",
    "vbp_adjustment_factor":   "hcs_silver.cms_vbp",
    "hrrp_adjustment_factor":  "hcs_silver.cms_hrrp",
    "hac_reduction_flag":      "hcs_silver.cms_hac_reduction",
    "mspb_score":              "hcs_silver.cms_mspb",
}

_BUILD_GOLD_SQL = """
WITH catchment AS (
  SELECT
    ccn,
    year,
    jsonb_agg(
      jsonb_build_object('zip', zip, 'share', share)
      ORDER BY share DESC
    ) FILTER (WHERE rank <= 10) AS top_zips
  FROM (
    SELECT
      ccn, year, zip, share,
      ROW_NUMBER() OVER (PARTITION BY ccn, year ORDER BY share DESC) AS rank
    FROM hcs_silver.cms_hospital_service_area
  ) ranked
  GROUP BY ccn, year
)
INSERT INTO hcs_gold.tavr_benchmark_inputs (
  ccn, year,
  facility_name, cbsa, hrr, state,
  facility_scale_band, bed_count, ownership, system_parent,
  teaching_proxy, cardiac_surgery_signal, cath_lab_signal,
  drg_266_discharges, drg_267_discharges, total_tavr_proxy,
  avg_payment, avg_charge, mcc_capture_proxy,
  yoy_growth, national_percentile, state_percentile,
  catchment_top_zips,
  vbp_adjustment_factor, hrrp_adjustment_factor,
  hac_reduction_flag, mspb_score,
  source_lineage,
  source_class, coverage_class, use_class, grain, as_of_date,
  source_id, confidence, caveat_text
)
SELECT
  py.ccn, py.year,
  hp.facility_name, hp.cbsa, hp.hrr,
  SUBSTRING(hp.county_fips FROM 1 FOR 2) AS state,
  hp.facility_scale_band, hp.bed_count, hp.ownership, hp.system_parent,
  hp.teaching_proxy, hp.cardiac_surgery_signal, hp.cath_lab_signal,
  py.drg_266_discharges, py.drg_267_discharges,
  py.drg_266_discharges + py.drg_267_discharges AS total_tavr_proxy,
  py.avg_payment, py.avg_charge, py.mcc_capture_proxy,
  py.yoy_growth, py.national_percentile, py.state_percentile,
  COALESCE(c.top_zips, '[]'::jsonb) AS catchment_top_zips,
  vbp.adjustment_factor AS vbp_adjustment_factor,
  hrrp.adjustment_factor AS hrrp_adjustment_factor,
  COALESCE(hac.is_reduced, false) AS hac_reduction_flag,
  mspb.mspb_score,
  %s::jsonb AS source_lineage,
  %s AS source_class,
  %s AS coverage_class,
  %s AS use_class,
  %s AS grain,
  NOW() AS as_of_date,
  %s AS source_id,
  %s AS confidence,
  %s AS caveat_text
FROM hcs_gold.tavr_program_year py
LEFT JOIN hcs_gold.tavr_hospital_profile hp ON hp.ccn = py.ccn
LEFT JOIN catchment c                       ON c.ccn = py.ccn AND c.year = py.year
LEFT JOIN hcs_silver.cms_vbp           vbp  ON vbp.ccn = py.ccn AND vbp.year = py.year
LEFT JOIN hcs_silver.cms_hrrp          hrrp ON hrrp.ccn = py.ccn AND hrrp.year = py.year
LEFT JOIN hcs_silver.cms_hac_reduction hac  ON hac.ccn = py.ccn AND hac.year = py.year
LEFT JOIN hcs_silver.cms_mspb          mspb ON mspb.ccn = py.ccn AND mspb.year = py.year
ON CONFLICT (ccn, year) DO UPDATE SET
  facility_name           = EXCLUDED.facility_name,
  cbsa                    = EXCLUDED.cbsa,
  hrr                     = EXCLUDED.hrr,
  state                   = EXCLUDED.state,
  facility_scale_band     = EXCLUDED.facility_scale_band,
  bed_count               = EXCLUDED.bed_count,
  ownership               = EXCLUDED.ownership,
  system_parent           = EXCLUDED.system_parent,
  teaching_proxy          = EXCLUDED.teaching_proxy,
  cardiac_surgery_signal  = EXCLUDED.cardiac_surgery_signal,
  cath_lab_signal         = EXCLUDED.cath_lab_signal,
  drg_266_discharges      = EXCLUDED.drg_266_discharges,
  drg_267_discharges      = EXCLUDED.drg_267_discharges,
  total_tavr_proxy        = EXCLUDED.total_tavr_proxy,
  avg_payment             = EXCLUDED.avg_payment,
  avg_charge              = EXCLUDED.avg_charge,
  mcc_capture_proxy       = EXCLUDED.mcc_capture_proxy,
  yoy_growth              = EXCLUDED.yoy_growth,
  national_percentile     = EXCLUDED.national_percentile,
  state_percentile        = EXCLUDED.state_percentile,
  catchment_top_zips      = EXCLUDED.catchment_top_zips,
  vbp_adjustment_factor   = EXCLUDED.vbp_adjustment_factor,
  hrrp_adjustment_factor  = EXCLUDED.hrrp_adjustment_factor,
  hac_reduction_flag      = EXCLUDED.hac_reduction_flag,
  mspb_score              = EXCLUDED.mspb_score,
  source_lineage          = EXCLUDED.source_lineage,
  as_of_date              = NOW(),
  confidence              = EXCLUDED.confidence,
  caveat_text             = EXCLUDED.caveat_text,
  updated_at              = NOW()
"""

_COUNT_ROWS_SQL = "SELECT COUNT(*) FROM hcs_gold.tavr_benchmark_inputs"


def load_tavr_benchmark_inputs_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Refresh hcs_gold.tavr_benchmark_inputs by joining Phase 1A outputs."""
    import json
    conn = get_connection()
    rows_written = 0
    total = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                _BUILD_GOLD_SQL,
                (
                    json.dumps(_SOURCE_LINEAGE),
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
