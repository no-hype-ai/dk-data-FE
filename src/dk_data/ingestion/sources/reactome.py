"""Reactome loader — inserts to mol_raw.reactome.

Loads Reactome pathway records (raw JSONB from the ContentService API)
into mol_raw.reactome using ON CONFLICT on the stId expression index.

Target table: mol_raw.reactome
Unique index: ON (response_body->>'stId') WHERE response_body->>'stId' IS NOT NULL
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_cursor

logger = logging.getLogger(__name__)


def load_reactome_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Load Reactome pathway records into mol_raw.reactome.

    Each record is stored as a raw JSONB blob. The Bronze model extracts
    typed fields using JSON path operators.

    Deduplication uses ON CONFLICT on the expression index over
    response_body->>'stId'. Records without a stId are skipped.

    Args:
        records: List of raw Reactome pathway dicts from ReactomeFetcher.
        source_hash: Optional content hash; unused but kept for interface consistency.

    Returns:
        Dict with status, records_fetched, records_inserted, errors.
    """
    if not records:
        logger.info("No Reactome records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    logger.info("Loading %d Reactome records into mol_raw.reactome", len(records))

    errors: List[str] = []
    inserted = 0
    skipped = 0

    sql = """
        INSERT INTO mol_raw.reactome (
            request_id, api_endpoint, api_version,
            response_status, response_body, source_id
        )
        VALUES (%s, 'https://reactome.org/ContentService', 'v1', 200, %s::JSONB, 'reactome')
        ON CONFLICT ((response_body->>'stId'))
        WHERE (response_body->>'stId') IS NOT NULL
        DO UPDATE SET
            response_body = EXCLUDED.response_body,
            ingested_at   = NOW()
        WHERE mol_raw.reactome.response_body IS DISTINCT FROM EXCLUDED.response_body
    """

    with get_cursor() as cur:
        for record in records:
            st_id = record.get("stId")
            if not st_id:
                skipped += 1
                continue
            try:
                cur.execute(sql, (f"reactome_{st_id}", json.dumps(record),))
                inserted += 1
            except Exception as exc:
                errors.append(f"stId={st_id}: {exc}")
                logger.warning("Reactome insert error for stId=%s: %s", st_id, exc)

    logger.info(
        "Reactome load complete: %d inserted/updated, %d skipped (no stId), %d errors",
        inserted, skipped, len(errors),
    )

    return {
        "status": "success" if not errors else "partial",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
