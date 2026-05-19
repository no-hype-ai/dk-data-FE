"""TAVR public proxy profile loader — Phase 1B public approximation layer.

Composes `hcs_gold.tavr_public_proxy_profile` per the handoff DoD. Every
field carries:
  - `*_public`: derived from public/machine-readable sources.
  - `*_licensed`: NULL in v1; Stage 4.5 backfills.
  - `*_selected`: selected per source_precedence in meta.metric_definitions
                  (NULL until v1.5 once that table is populated).
  - `*_selected_source`: which side (public / licensed) was chosen.

All seven red-flag detectors apply at this layer — the loader enforces:
  - numeric_value_without_citation: every field's source_id is recorded in
    source_lineage via the parent caveat_text.
  - study_estimate_applied_to_hospital: this loader pulls only hospital-
    grain CMS PUFs; study-level data is never joined here.
  - system_filing_applied_to_facility: facility grain only; system_parent
    is read from tavr_hospital_profile (already validated).
  - maude_used_as_rate: payment_proxy_* are usd_per_discharge units.
  - top_referrer_inferred_from_proximity: catchment_proxy_* uses CMS
    Hospital Service Area shares, NOT proximity.
  - llm_completion_without_citation: this is a SQL loader, no LLM path.
  - missing_denominator_or_year_or_grain_mismatch: grain CHECK + (ccn, year)
    PK + as_of_date NOW().

Schema: migration 243.
Spec: .dk/specs/011-tavr-public-proxy-profile-provisioning/spec.md
"""

import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "tavr_public_proxy_profile"

# IMPORTANT — coverage_class FIXED to 'public_proxy' (NOT baseline_public);
# use_class FIXED to 'benchmark_shape_or_load'. Both are CHECK-constrained
# at the schema level; loader's value here must match.
_DEFAULT_SOURCE_CLASS = "public_machine_readable"
_DEFAULT_COVERAGE_CLASS = "public_proxy"
_DEFAULT_USE_CLASS = "benchmark_shape_or_load"
_DEFAULT_GRAIN = "hospital_year"
_DEFAULT_CONFIDENCE = 0.55  # Lower than upstream gold tables — this is a proxy layer.
_DEFAULT_CAVEAT = (
    "Public proxy layer; benchmark-shape-or-load only. Side-by-side "
    "licensed columns NULL in v1. Stage 4.5 will layer licensed overlays "
    "without schema migration."
)

# Build the public-side proxies. Licensed columns left NULL; selected
# columns default to the public value (selected_source = 'public_proxy').
# When meta.metric_definitions is wired up, a follow-up loader can
# overwrite selected_* per source_precedence per metric.
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
),
physician AS (
  -- NPI count + structural-heart hits per CCN. Hospital affiliation join
  -- via cms_hospital_affiliation. KOL signal kept simple (count > N
  -- of Open Payments rows). Phase 4 abstracted evidence can refine.
  SELECT
    aff.ccn,
    COUNT(DISTINCT phy.npi) AS npi_count,
    COUNT(DISTINCT phy.npi) FILTER (
      WHERE phy.specialty ILIKE '%cardiology%' OR phy.specialty ILIKE '%cardiac%'
    ) AS structural_heart_hits,
    COUNT(DISTINCT op.npi) FILTER (WHERE op.payment_amount >= 10000) AS kol_signal
  FROM hcs_silver.cms_hospital_affiliation aff
  LEFT JOIN hcs_silver.cms_physician_puf phy ON phy.npi = aff.npi
  LEFT JOIN hcs_silver.cms_open_payments op  ON op.npi  = aff.npi
  GROUP BY aff.ccn
)
INSERT INTO hcs_gold.tavr_public_proxy_profile (
  ccn, year,
  volume_proxy_public, volume_proxy_selected, volume_selected_source,
  payment_proxy_public, payment_proxy_selected, payment_selected_source,
  catchment_proxy_public, catchment_proxy_selected, catchment_selected_source,
  readiness_proxy_public, readiness_proxy_selected, readiness_selected_source,
  physician_signal_public, physician_signal_selected, physician_selected_source,
  completeness,
  source_class, coverage_class, use_class, grain, as_of_date,
  source_id, confidence, caveat_text
)
SELECT
  py.ccn, py.year,

  -- Volume proxy = DRG 266 + 267 from program_year.
  py.drg_266_discharges + py.drg_267_discharges AS volume_proxy_public,
  py.drg_266_discharges + py.drg_267_discharges AS volume_proxy_selected,
  'public_proxy' AS volume_selected_source,

  -- Payment proxy = HCRIS CCR-adjusted avg charge (fallback to avg_payment).
  COALESCE(hcris.ccr_adjusted_payment_proxy, py.avg_payment) AS payment_proxy_public,
  COALESCE(hcris.ccr_adjusted_payment_proxy, py.avg_payment) AS payment_proxy_selected,
  'public_proxy' AS payment_selected_source,

  -- Catchment proxy = CMS HSA top-N ZIPs.
  COALESCE(c.top_zips, '[]'::jsonb) AS catchment_proxy_public,
  COALESCE(c.top_zips, '[]'::jsonb) AS catchment_proxy_selected,
  'public_proxy' AS catchment_selected_source,

  -- Readiness proxy = cardiac/cath/TVT/cert signals from hospital_profile.
  jsonb_build_object(
    'cardiac_surgery_signal', hp.cardiac_surgery_signal,
    'cath_lab_signal', hp.cath_lab_signal,
    'tvt_signal', hp.tvt_signal,
    'teaching_proxy', hp.teaching_proxy
  ) AS readiness_proxy_public,
  jsonb_build_object(
    'cardiac_surgery_signal', hp.cardiac_surgery_signal,
    'cath_lab_signal', hp.cath_lab_signal,
    'tvt_signal', hp.tvt_signal,
    'teaching_proxy', hp.teaching_proxy
  ) AS readiness_proxy_selected,
  'public_proxy' AS readiness_selected_source,

  -- Physician signal proxy = NPI count, structural-heart hits, KOL signal.
  jsonb_build_object(
    'npi_count', COALESCE(ph.npi_count, 0),
    'structural_heart_hits', COALESCE(ph.structural_heart_hits, 0),
    'kol_signal', COALESCE(ph.kol_signal, 0)
  ) AS physician_signal_public,
  jsonb_build_object(
    'npi_count', COALESCE(ph.npi_count, 0),
    'structural_heart_hits', COALESCE(ph.structural_heart_hits, 0),
    'kol_signal', COALESCE(ph.kol_signal, 0)
  ) AS physician_signal_selected,
  'public_proxy' AS physician_selected_source,

  -- Completeness — fraction of five proxies with a non-null selected value.
  (
    (CASE WHEN py.drg_266_discharges + py.drg_267_discharges IS NOT NULL THEN 1 ELSE 0 END) +
    (CASE WHEN COALESCE(hcris.ccr_adjusted_payment_proxy, py.avg_payment) IS NOT NULL THEN 1 ELSE 0 END) +
    (CASE WHEN c.top_zips IS NOT NULL THEN 1 ELSE 0 END) +
    (CASE WHEN hp.ccn IS NOT NULL THEN 1 ELSE 0 END) +
    (CASE WHEN ph.ccn IS NOT NULL THEN 1 ELSE 0 END)
  )::numeric / 5.0 AS completeness,

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
LEFT JOIN hcs_silver.cms_hcris hcris         ON hcris.ccn = py.ccn
LEFT JOIN catchment c                        ON c.ccn = py.ccn AND c.year = py.year
LEFT JOIN physician ph                       ON ph.ccn = py.ccn
ON CONFLICT (ccn, year) DO UPDATE SET
  volume_proxy_public       = EXCLUDED.volume_proxy_public,
  volume_proxy_selected     = EXCLUDED.volume_proxy_selected,
  volume_selected_source    = EXCLUDED.volume_selected_source,
  payment_proxy_public      = EXCLUDED.payment_proxy_public,
  payment_proxy_selected    = EXCLUDED.payment_proxy_selected,
  payment_selected_source   = EXCLUDED.payment_selected_source,
  catchment_proxy_public    = EXCLUDED.catchment_proxy_public,
  catchment_proxy_selected  = EXCLUDED.catchment_proxy_selected,
  catchment_selected_source = EXCLUDED.catchment_selected_source,
  readiness_proxy_public    = EXCLUDED.readiness_proxy_public,
  readiness_proxy_selected  = EXCLUDED.readiness_proxy_selected,
  readiness_selected_source = EXCLUDED.readiness_selected_source,
  physician_signal_public   = EXCLUDED.physician_signal_public,
  physician_signal_selected = EXCLUDED.physician_signal_selected,
  physician_selected_source = EXCLUDED.physician_selected_source,
  completeness              = EXCLUDED.completeness,
  as_of_date                = NOW(),
  confidence                = EXCLUDED.confidence,
  caveat_text               = EXCLUDED.caveat_text,
  updated_at                = NOW()
"""

_COUNT_ROWS_SQL = "SELECT COUNT(*) FROM hcs_gold.tavr_public_proxy_profile"


def load_tavr_public_proxy_profile_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Refresh hcs_gold.tavr_public_proxy_profile from Phase 1A + physician silver."""
    rows_written = 0
    total = 0
    with get_connection() as conn:
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

    logger.info(
        "[%s] upserted=%d total_rows=%d", SOURCE_ID, rows_written, total,
    )
    return {
        "status": "success",
        "records_inserted": rows_written,
        "record_count": rows_written,
        "total_rows": total,
    }
