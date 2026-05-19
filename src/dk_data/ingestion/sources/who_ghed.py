"""WHO GHED loader — inserts to hcs_raw.who_ghed.

Loads WHO Global Health Expenditure Database records (raw JSONB from the
bulk CSV or GHO API fallback) into hcs_raw.who_ghed using ON CONFLICT
on the (country, year, indicator) composite expression index.

Target table: hcs_raw.who_ghed
Unique index: ON (
    response_body->>'country',
    response_body->>'year',
    response_body->>'indicator'
) — or equivalent composite from the CSV column names.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_cursor

logger = logging.getLogger(__name__)


def _dedup_key(record: Dict[str, Any]) -> Optional[str]:
    """Build a dedup key from the record.

    CSV rows use column names like 'country', 'year', 'indicator'.
    GHO fallback rows use 'SpatialDim', 'TimeDim', 'IndicatorCode'.
    """
    # CSV bulk format
    country = record.get("country") or record.get("SpatialDim") or record.get("COUNTRY") or ""
    year = record.get("year") or record.get("TimeDim") or record.get("YEAR") or ""
    indicator = (
        record.get("indicator") or record.get("IndicatorCode")
        or record.get("INDICATOR") or ""
    )
    if not country or not year:
        return None
    return f"{country}_{year}_{indicator}"


def load_who_ghed_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Load WHO GHED records into hcs_raw.who_ghed.

    Each record is stored as a raw JSONB blob. The Bronze model extracts
    typed fields using JSON path operators.

    Args:
        records: List of raw WHO GHED dicts from WHOGHEDFetcher.
        source_hash: Optional content hash; unused but kept for interface consistency.

    Returns:
        Dict with status, records_fetched, records_inserted, errors.
    """
    if not records:
        logger.info("No WHO GHED records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    logger.info("Loading %d WHO GHED records into hcs_raw.who_ghed", len(records))

    errors: List[str] = []
    inserted = 0
    skipped = 0

    sql = """
        INSERT INTO hcs_raw.who_ghed (
            request_id, api_endpoint, api_version,
            response_status, response_body, source_id
        )
        VALUES (%s, 'https://apps.who.int/nha/database', 'v1', 200, %s::JSONB, 'who_ghed')
        ON CONFLICT (request_id)
        DO UPDATE SET
            response_body = EXCLUDED.response_body,
            ingested_at   = NOW()
        WHERE hcs_raw.who_ghed.response_body IS DISTINCT FROM EXCLUDED.response_body
    """

    with get_cursor() as cur:
        for record in records:
            dedup = _dedup_key(record)
            if not dedup:
                skipped += 1
                continue
            request_id = f"who_ghed_{dedup}"
            try:
                cur.execute("SAVEPOINT sp")
                cur.execute(sql, (request_id, json.dumps(record)))
                cur.execute("RELEASE SAVEPOINT sp")
                inserted += 1
            except Exception as exc:
                cur.execute("ROLLBACK TO SAVEPOINT sp")
                errors.append(f"key={dedup}: {exc}")
                logger.warning(
                    "WHO GHED insert error for key=%s: %s", dedup, exc
                )

    logger.info(
        "WHO GHED load complete: %d inserted/updated, %d skipped, %d errors",
        inserted, skipped, len(errors),
    )

    return {
        "status": "success" if not errors else "partial",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
