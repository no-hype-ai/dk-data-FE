"""FDA Purple Book loader — inserts to mol_raw.purple_book.

Loads FDA Purple Book (BLA) application records (raw JSONB from the
openFDA Drugs@FDA API) into mol_raw.purple_book using ON CONFLICT on
the application_number expression index.

Target table: mol_raw.purple_book
Unique index: ON (response_body->>'application_number')
              WHERE response_body->>'application_number' IS NOT NULL
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_cursor

logger = logging.getLogger(__name__)


def load_purple_book_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Load FDA Purple Book BLA records into mol_raw.purple_book.

    Each record is stored as a raw JSONB blob. The Bronze model extracts
    typed fields using JSON path operators.

    Deduplication uses ON CONFLICT on the expression index over
    response_body->>'application_number'. Records without an
    application_number are skipped.

    Args:
        records: List of raw BLA application dicts from PurpleBookFetcher.
        source_hash: Optional content hash; unused but kept for interface consistency.

    Returns:
        Dict with status, records_fetched, records_inserted, errors.
    """
    if not records:
        logger.info("No Purple Book records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    logger.info(
        "Loading %d Purple Book records into mol_raw.purple_book", len(records)
    )

    errors: List[str] = []
    inserted = 0
    skipped = 0

    sql = """
        INSERT INTO mol_raw.purple_book (
            request_id, api_endpoint, api_version,
            response_status, response_body, source_id
        )
        VALUES (%s, 'https://api.fda.gov/drug/drugsfda.json', 'v1', 200, %s::JSONB, 'purple_book')
        ON CONFLICT ((response_body->>'application_number'))
        WHERE (response_body->>'application_number') IS NOT NULL
        DO UPDATE SET
            response_body = EXCLUDED.response_body,
            ingested_at   = NOW()
        WHERE mol_raw.purple_book.response_body IS DISTINCT FROM EXCLUDED.response_body
    """

    with get_cursor() as cur:
        for record in records:
            app_num = record.get("application_number")
            if not app_num:
                skipped += 1
                continue
            try:
                cur.execute(sql, (f"purple_book_{app_num}", json.dumps(record),))
                inserted += 1
            except Exception as exc:
                errors.append(f"application_number={app_num}: {exc}")
                logger.warning(
                    "Purple Book insert error for application_number=%s: %s",
                    app_num, exc,
                )

    logger.info(
        "Purple Book load complete: %d inserted/updated, %d skipped (no app_num), %d errors",
        inserted, skipped, len(errors),
    )

    return {
        "status": "success" if not errors else "partial",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
