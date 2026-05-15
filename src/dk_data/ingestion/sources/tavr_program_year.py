"""TAVR program-year loader (data-researcher §4.5 MedPAR-like baseline).

Composes `hcs_gold.tavr_program_year` from CMS Inpatient PUF silver
filtered to DRG 266/267. Percentiles computed via PostgreSQL window
functions (PERCENT_RANK) over national + state partitions.

Red-flag gates enforced:
  - missing_denominator_or_year_or_grain_mismatch — grain CHECK constraint
    + NOT NULL year + non-null as_of_date set by NOW().
  - maude_used_as_rate — avg_payment / avg_charge are usd_per_discharge
    units, documented in COMMENT ON COLUMN, not rate-bearing.

Schema: migration 241.
Spec: .dk/specs/009-tavr-program-year-provisioning/spec.md
"""

import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "tavr_program_year"

_DEFAULT_SOURCE_CLASS = "public_machine_readable"
_DEFAULT_COVERAGE_CLASS = "baseline_public"
_DEFAULT_USE_CLASS = "benchmark_shape_or_load"
_DEFAULT_GRAIN = "hospital_year"
_DEFAULT_CONFIDENCE = 0.75
_DEFAULT_CAVEAT = (
    "DRG 266/267 Medicare FFS proxy; hospital-year; "
    "benchmark-shape only; not all-payer TAVR volume"
)

# Aggregates DRG 266 + 267 rows per (ccn, year), computes MCC capture proxy,
# YoY growth, national and state percentiles in a single CTE pipeline.
# The exact silver column names below should be verified against the live
# schema before merge — see open question in PR body.
_BUILD_GOLD_SQL = """
WITH agg AS (
  SELECT
    ccn,
    year,
    SUM(CASE WHEN ms_drg = '266' THEN discharges ELSE 0 END) AS drg_266_discharges,
    SUM(CASE WHEN ms_drg = '267' THEN discharges ELSE 0 END) AS drg_267_discharges,
    AVG(avg_medicare_payment_amt) AS avg_payment,
    AVG(avg_submitted_charge_amt) AS avg_charge,
    MAX(state) AS state
  FROM hcs_silver.cms_inpatient_puf
  WHERE ms_drg IN ('266', '267')
  GROUP BY ccn, year
),
ranked AS (
  SELECT
    ccn, year, state,
    drg_266_discharges,
    drg_267_discharges,
    avg_payment, avg_charge,
    CASE
      WHEN (drg_266_discharges + drg_267_discharges) > 0
      THEN drg_266_discharges::numeric / (drg_266_discharges + drg_267_discharges)
      ELSE NULL
    END AS mcc_capture_proxy,
    PERCENT_RANK() OVER (
      PARTITION BY year
      ORDER BY drg_266_discharges + drg_267_discharges
    ) AS national_percentile,
    PERCENT_RANK() OVER (
      PARTITION BY year, state
      ORDER BY drg_266_discharges + drg_267_discharges
    ) AS state_percentile,
    LAG(drg_266_discharges + drg_267_discharges)
      OVER (PARTITION BY ccn ORDER BY year) AS prev_total
  FROM agg
)
INSERT INTO hcs_gold.tavr_program_year (
  ccn, year, drg_266_discharges, drg_267_discharges,
  avg_payment, avg_charge, mcc_capture_proxy,
  yoy_growth, national_percentile, state_percentile,
  tvt_signal,
  source_class, coverage_class, use_class, grain, as_of_date,
  source_id, confidence, caveat_text
)
SELECT
  ccn, year, drg_266_discharges, drg_267_discharges,
  avg_payment, avg_charge, mcc_capture_proxy,
  CASE
    WHEN prev_total IS NULL OR prev_total = 0 THEN NULL
    ELSE ((drg_266_discharges + drg_267_discharges)::numeric - prev_total) / prev_total
  END AS yoy_growth,
  national_percentile,
  state_percentile,
  NULL AS tvt_signal,
  %s AS source_class,
  %s AS coverage_class,
  %s AS use_class,
  %s AS grain,
  NOW() AS as_of_date,
  %s AS source_id,
  %s AS confidence,
  %s AS caveat_text
FROM ranked
ON CONFLICT (ccn, year) DO UPDATE SET
  drg_266_discharges    = EXCLUDED.drg_266_discharges,
  drg_267_discharges    = EXCLUDED.drg_267_discharges,
  avg_payment           = EXCLUDED.avg_payment,
  avg_charge            = EXCLUDED.avg_charge,
  mcc_capture_proxy     = EXCLUDED.mcc_capture_proxy,
  yoy_growth            = EXCLUDED.yoy_growth,
  national_percentile   = EXCLUDED.national_percentile,
  state_percentile      = EXCLUDED.state_percentile,
  -- tvt_signal intentionally NOT overwritten — Phase 4 evidence backfills it.
  as_of_date            = NOW(),
  confidence            = EXCLUDED.confidence,
  caveat_text           = EXCLUDED.caveat_text,
  updated_at            = NOW()
"""

_COUNT_ROWS_SQL = "SELECT COUNT(*) FROM hcs_gold.tavr_program_year"


def load_tavr_program_year_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Refresh hcs_gold.tavr_program_year from CMS Inpatient PUF silver."""
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
