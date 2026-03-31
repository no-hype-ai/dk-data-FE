"""WHO GHO loader — inserts to mol_raw.who_gho.

Loads WHO GHO indicator records (raw JSONB from the OData API) into
mol_raw.who_gho using ON CONFLICT on the IndicatorCode expression index.

Target table: mol_raw.who_gho
Unique index: ON (response_body->>'IndicatorCode')
              WHERE response_body->>'IndicatorCode' IS NOT NULL
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_cursor

logger = logging.getLogger(__name__)


def load_who_gho_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Load WHO GHO indicator records into mol_raw.who_gho.

    Each record is stored as a raw JSONB blob. The Bronze model extracts
    typed fields using JSON path operators.

    Deduplication uses ON CONFLICT on the expression index over
    response_body->>'IndicatorCode'. Records without an IndicatorCode
    are skipped.

    Args:
        records: List of raw WHO GHO indicator dicts from WHOGHOFetcher.
        source_hash: Optional content hash; unused but kept for interface consistency.

    Returns:
        Dict with status, records_fetched, records_inserted, errors.
    """
    if not records:
        logger.info("No WHO GHO records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    logger.info("Loading %d WHO GHO records into mol_raw.who_gho", len(records))

    errors: List[str] = []
    inserted = 0
    skipped = 0

    sql = """
        INSERT INTO mol_raw.who_gho (response_body, source_id)
        VALUES (%s::JSONB, 'who_gho')
        ON CONFLICT ((response_body->>'IndicatorCode'))
        WHERE (response_body->>'IndicatorCode') IS NOT NULL
        DO UPDATE SET
            response_body = EXCLUDED.response_body,
            ingested_at   = NOW()
        WHERE mol_raw.who_gho.response_body IS DISTINCT FROM EXCLUDED.response_body
    """

    with get_cursor() as cur:
        for record in records:
            indicator_code = record.get("IndicatorCode")
            if not indicator_code:
                skipped += 1
                continue
            try:
                cur.execute(sql, (json.dumps(record),))
                inserted += 1
            except Exception as exc:
                errors.append(f"IndicatorCode={indicator_code}: {exc}")
                logger.warning(
                    "WHO GHO insert error for IndicatorCode=%s: %s",
                    indicator_code, exc,
                )

    logger.info(
        "WHO GHO load complete: %d inserted/updated, %d skipped (no code), %d errors",
        inserted, skipped, len(errors),
    )

    return {
        "status": "success" if not errors else "partial",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
