"""World Bank Health loader — inserts to hcs_raw.worldbank_health.

Loads World Bank health indicator records (normalized JSON from the v2 API)
into hcs_raw.worldbank_health using ON CONFLICT on request_id
(indicator_code + country_code + year).

Target table: hcs_raw.worldbank_health
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_cursor

logger = logging.getLogger(__name__)


def load_worldbank_health_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Load World Bank health indicator records into hcs_raw.worldbank_health.

    Each record is stored as a raw JSONB blob. The Bronze model extracts
    typed fields using JSON path operators.

    Deduplication uses request_id = '{indicator_code}_{country_code}_{year}'.

    Args:
        records: List of normalized World Bank indicator dicts.
        source_hash: Optional content hash; unused but kept for interface consistency.

    Returns:
        Dict with status, records_fetched, records_inserted, errors.
    """
    if not records:
        logger.info("No World Bank health records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    logger.info(
        "Loading %d World Bank health records into hcs_raw.worldbank_health",
        len(records),
    )

    errors: List[str] = []
    inserted = 0
    skipped = 0

    sql = """
        INSERT INTO hcs_raw.worldbank_health (
            request_id, api_endpoint, api_version,
            response_status, response_body, source_id
        )
        VALUES (%s, 'https://api.worldbank.org/v2', 'v2', 200, %s::JSONB, 'worldbank_health')
        ON CONFLICT (request_id)
        DO UPDATE SET
            response_body = EXCLUDED.response_body,
            ingested_at   = NOW()
        WHERE hcs_raw.worldbank_health.response_body IS DISTINCT FROM EXCLUDED.response_body
    """

    with get_cursor() as cur:
        for record in records:
            indicator = record.get("indicator_code", "")
            country = record.get("country_code", "")
            year = record.get("year", "")
            if not indicator or not country or not year:
                skipped += 1
                continue

            request_id = f"wb_{indicator}_{country}_{year}"
            try:
                cur.execute("SAVEPOINT sp")
                cur.execute(sql, (request_id, json.dumps(record)))
                cur.execute("RELEASE SAVEPOINT sp")
                inserted += 1
            except Exception as exc:
                cur.execute("ROLLBACK TO SAVEPOINT sp")
                errors.append(f"{request_id}: {exc}")
                logger.warning(
                    "World Bank insert error for %s: %s", request_id, exc
                )

    logger.info(
        "World Bank health load complete: %d inserted/updated, %d skipped, %d errors",
        inserted, skipped, len(errors),
    )

    return {
        "status": "success" if not errors else "partial",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
