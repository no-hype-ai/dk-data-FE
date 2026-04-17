"""OECD Health loader — inserts to hcs_raw.oecd_health.

Loads OECD health statistics records (from SDMX CSV or JSON) into
hcs_raw.oecd_health using ON CONFLICT on request_id.

Target table: hcs_raw.oecd_health
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_cursor

logger = logging.getLogger(__name__)


def _make_request_id(record: Dict[str, Any]) -> Optional[str]:
    """Build a deterministic request_id from SDMX CSV row fields.

    SDMX CSV rows typically have: REF_AREA, MEASURE, TIME_PERIOD, etc.
    We hash the full record to ensure uniqueness.
    """
    # Try standard SDMX dimension columns
    ref_area = record.get("REF_AREA", record.get("LOCATION", ""))
    measure = record.get("MEASURE", record.get("INDICATOR", ""))
    time_period = record.get("TIME_PERIOD", record.get("TIME", ""))

    if ref_area and time_period:
        return f"oecd_{ref_area}_{measure}_{time_period}"

    # For obs_key format (JSON fallback)
    obs_key = record.get("obs_key", "")
    if obs_key:
        return f"oecd_obs_{obs_key}"

    # Last resort: hash the entire record
    content = json.dumps(record, sort_keys=True)
    return f"oecd_{hashlib.md5(content.encode()).hexdigest()[:16]}"


def load_oecd_health_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Load OECD health statistics records into hcs_raw.oecd_health.

    Each record is stored as a raw JSONB blob. The Bronze model extracts
    typed fields using JSON path operators.

    Args:
        records: List of OECD SDMX row dicts from OECDHealthFetcher.
        source_hash: Optional content hash; unused but kept for interface consistency.

    Returns:
        Dict with status, records_fetched, records_inserted, errors.
    """
    if not records:
        logger.info("No OECD health records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    logger.info(
        "Loading %d OECD health records into hcs_raw.oecd_health", len(records)
    )

    errors: List[str] = []
    inserted = 0
    skipped = 0

    sql = """
        INSERT INTO hcs_raw.oecd_health (
            request_id, api_endpoint, api_version,
            response_status, response_body, source_id
        )
        VALUES (%s, 'https://sdmx.oecd.org/public/rest', 'v2', 200, %s::JSONB, 'oecd_health')
        ON CONFLICT (request_id)
        DO UPDATE SET
            response_body = EXCLUDED.response_body,
            ingested_at   = NOW()
        WHERE hcs_raw.oecd_health.response_body IS DISTINCT FROM EXCLUDED.response_body
    """

    with get_cursor() as cur:
        for record in records:
            request_id = _make_request_id(record)
            if not request_id:
                skipped += 1
                continue
            try:
                cur.execute("SAVEPOINT sp")
                cur.execute(sql, (request_id, json.dumps(record)))
                cur.execute("RELEASE SAVEPOINT sp")
                inserted += 1
            except Exception as exc:
                cur.execute("ROLLBACK TO SAVEPOINT sp")
                errors.append(f"{request_id}: {exc}")
                logger.warning(
                    "OECD health insert error for %s: %s", request_id, exc
                )

    logger.info(
        "OECD health load complete: %d inserted/updated, %d skipped, %d errors",
        inserted, skipped, len(errors),
    )

    return {
        "status": "success" if not errors else "partial",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
