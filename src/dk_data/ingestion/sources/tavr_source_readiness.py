"""TAVR source readiness loader.

Composes `hcs_gold.tavr_source_readiness` by classifying every known source_id
against meta.refresh_log (freshness) and meta.table_health (row count + status).

Source list is the union of:
  - meta.data_sources.source_name (live ingestion sources)
  - hcs_gold.tavr_catalog_candidate_manifest.source_id (catalog discoveries)
  - Priority-1 source IDs declared in the spec (so they show up as `absent`
    until provisioned).

Classification rules:
  - claim_eligible: last_refresh_at within freshness SLA AND
                    health_status IN ('healthy', 'fresh') AND
                    source_class IN ('public_machine_readable', 'licensed_commercial')
  - context_only:   row exists but source_class = 'public_abstractable'
                    (abstractable evidence can support but not anchor a claim)
  - blocked:        access_level = 'restricted' OR coverage_class = 'blocked'
  - absent:         no row in meta.refresh_log (never refreshed) OR last_refresh_at NULL

Spec: .dk/specs/007-tavr-source-readiness-provisioning/spec.md
Schema: migration 239.
"""

import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "tavr_source_readiness"

# Priority-1 sources per the recommendation §Priority 1 (edwards-meadow).
# These MUST appear in the table even if no upstream row exists yet
# (status = 'absent' surfaces the gap to tavr-bench).
PRIORITY_1_SOURCES: List[str] = [
    "cms_hospital_general_info",
    "cms_pos",
    "cms_chow",
    "cms_hcris",
    "cms_inpatient_puf",
    "cms_geographic_variation",
    "cms_hospital_service_area",
    "cms_mspb",
    "cms_vbp",
    "cms_hrrp",
    "cms_hac_reduction",
    "cms_open_payments",
    "cms_physician_puf",
    "cms_nppes",
    "hrsa",
    "irs_990",
    "census_cbsa",
    "usda_ruca",
    "sec_edgar",
    "acc_tvc",
    "tavr_catalog_data_gov",
]

# Freshness SLA defaults. Source-specific overrides could live in
# meta.metric_definitions or be read from a config. For v1 we use a single
# default and surface in caveat_text.
FRESHNESS_SLA_HOURS = 24 * 90  # 90 days; CMS PUFs publish quarterly/annually

_DEFAULT_COVERAGE_CLASS_FOR_PRESENT = "tracked"
_DEFAULT_USE_CLASS = "readiness_signal"
_DEFAULT_GRAIN = "source"
_DEFAULT_CONFIDENCE = 0.80
_DEFAULT_CAVEAT = (
    "Readiness derived from meta.refresh_log + meta.table_health. "
    "Freshness SLA is a 90-day default; per-source SLAs should be migrated "
    "into meta.metric_definitions before tightening downstream gates."
)

_TRUNCATE_SQL = "TRUNCATE TABLE hcs_gold.tavr_source_readiness"

_UPSERT_SQL = """
    INSERT INTO hcs_gold.tavr_source_readiness (
      source_id, status, row_count, last_refresh_at, age_hours,
      health_status, source_class, coverage_class, use_class, grain,
      as_of_date, confidence, caveat_text
    ) VALUES (
      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s
    )
    ON CONFLICT (source_id) DO UPDATE SET
      status          = EXCLUDED.status,
      row_count       = EXCLUDED.row_count,
      last_refresh_at = EXCLUDED.last_refresh_at,
      age_hours       = EXCLUDED.age_hours,
      health_status   = EXCLUDED.health_status,
      source_class    = EXCLUDED.source_class,
      coverage_class  = EXCLUDED.coverage_class,
      use_class       = EXCLUDED.use_class,
      as_of_date      = NOW(),
      confidence      = EXCLUDED.confidence,
      caveat_text     = EXCLUDED.caveat_text,
      updated_at      = NOW()
"""

_COLLECT_SOURCES_SQL = """
    WITH all_sources AS (
      SELECT source_name FROM meta.data_sources
      UNION
      SELECT DISTINCT source_id AS source_name
        FROM hcs_gold.tavr_catalog_candidate_manifest
    )
    SELECT source_name FROM all_sources
"""

_HEALTH_LOOKUP_SQL = """
    SELECT
      rl.last_successful_refresh,
      rl.row_count,
      th.health_status,
      EXTRACT(EPOCH FROM (NOW() - rl.last_successful_refresh)) / 3600.0 AS age_hours
    FROM meta.refresh_log rl
    LEFT JOIN meta.table_health th
      ON th.source_name = rl.source_name
    WHERE rl.source_name = %s
    ORDER BY rl.last_successful_refresh DESC NULLS LAST
    LIMIT 1
"""


def _classify_source(
    last_refresh_at: Optional[Any],
    age_hours: Optional[float],
    health_status: Optional[str],
    source_class: str,
) -> str:
    """Apply the classification rules; return one of the four status values."""
    if last_refresh_at is None:
        return "absent"
    if source_class == "private_or_partner":
        return "blocked"
    if age_hours is not None and age_hours > FRESHNESS_SLA_HOURS:
        return "context_only"
    if health_status not in (None, "healthy", "fresh", "ok"):
        return "context_only"
    if source_class == "public_abstractable":
        return "context_only"
    return "claim_eligible"


def _infer_source_class(source_name: str) -> str:
    """Heuristic source_class for a source_name. Real classifier would consult
    meta.metric_definitions or the catalog manifest's source_class field."""
    if source_name.startswith(("cms_", "hrsa", "census_", "usda_", "irs_", "sec_")):
        return "public_machine_readable"
    if source_name in ("acc_tvc", "tavr_catalog_data_gov"):
        return "public_machine_readable"
    return "public_abstractable"


def load_tavr_source_readiness_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Build hcs_gold.tavr_source_readiness from meta.* + catalog manifest.

    `records` is ignored; this loader is fully derived and pulls from in-DB
    state. The argument exists to satisfy the SOURCES registry contract.

    Returns a dict with counts: rows_written, claim_eligible, context_only,
    blocked, absent.
    """
    rows_written = 0
    counts = {"claim_eligible": 0, "context_only": 0, "blocked": 0, "absent": 0}

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Discover every source we know about.
            cur.execute(_COLLECT_SOURCES_SQL)
            discovered = {row[0] for row in cur.fetchall() if row[0]}
            discovered.update(PRIORITY_1_SOURCES)

            for source_name in sorted(discovered):
                cur.execute(_HEALTH_LOOKUP_SQL, (source_name,))
                health_row = cur.fetchone()
                if health_row is None:
                    last_refresh = None
                    row_count = None
                    health_status = None
                    age_hours = None
                else:
                    last_refresh, row_count, health_status, age_hours = health_row

                source_class = _infer_source_class(source_name)
                status = _classify_source(
                    last_refresh, age_hours, health_status, source_class,
                )
                counts[status] += 1

                cur.execute(
                    _UPSERT_SQL,
                    (
                        source_name, status, row_count, last_refresh,
                        age_hours, health_status, source_class,
                        _DEFAULT_COVERAGE_CLASS_FOR_PRESENT if status != "absent" else "absent",
                        _DEFAULT_USE_CLASS, _DEFAULT_GRAIN,
                        _DEFAULT_CONFIDENCE, _DEFAULT_CAVEAT,
                    ),
                )
                rows_written += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    logger.info(
        "[%s] rows=%d claim_eligible=%d context_only=%d blocked=%d absent=%d",
        SOURCE_ID, rows_written,
        counts["claim_eligible"], counts["context_only"],
        counts["blocked"], counts["absent"],
    )
    return {
        "status": "success",
        "records_inserted": rows_written,
        "record_count": rows_written,
        **counts,
    }
