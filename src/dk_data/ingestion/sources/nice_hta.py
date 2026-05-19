"""NICE HTA loader — inserts to mol_raw.nice_hta.

Loads NICE guidance records (raw JSONB from the NICE guidance API) into
mol_raw.nice_hta using ON CONFLICT on the guidance Id expression index.

Target table: mol_raw.nice_hta
Unique index: ON (response_body->>'Id') WHERE response_body->>'Id' IS NOT NULL
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_cursor

logger = logging.getLogger(__name__)


def load_nice_hta_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Load NICE guidance records into mol_raw.nice_hta.

    Each record is stored as a raw JSONB blob. The Bronze model extracts
    typed fields using JSON path operators.

    Deduplication uses ON CONFLICT on the expression index over
    response_body->>'Id'. Records without an Id are skipped.

    Args:
        records: List of raw NICE guidance dicts from NICEHTAFetcher.
        source_hash: Optional content hash; unused but kept for interface consistency.

    Returns:
        Dict with status, records_fetched, records_inserted, errors.
    """
    if not records:
        logger.info("No NICE HTA records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    logger.info("Loading %d NICE HTA records into mol_raw.nice_hta", len(records))

    errors: List[str] = []
    inserted = 0
    skipped = 0

    sql = """
        INSERT INTO mol_raw.nice_hta (
            request_id, api_endpoint, api_version,
            response_status, response_body, source_id
        )
        VALUES (%s, 'https://api.nice.org.uk/services/guidance', 'v1', 200, %s::JSONB, 'nice_hta')
        ON CONFLICT ((response_body->>'Id'))
        WHERE (response_body->>'Id') IS NOT NULL
        DO UPDATE SET
            response_body = EXCLUDED.response_body,
            ingested_at   = NOW()
        WHERE mol_raw.nice_hta.response_body IS DISTINCT FROM EXCLUDED.response_body
    """

    with get_cursor() as cur:
        for record in records:
            doc_id = record.get("Id")
            if not doc_id:
                skipped += 1
                continue
            try:
                cur.execute(sql, (f"nice_hta_{doc_id}", json.dumps(record),))
                inserted += 1
            except Exception as exc:
                errors.append(f"Id={doc_id}: {exc}")
                logger.warning(
                    "NICE HTA insert error for Id=%s: %s", doc_id, exc
                )

    logger.info(
        "NICE HTA load complete: %d inserted/updated, %d skipped (no Id), %d errors",
        inserted, skipped, len(errors),
    )

    return {
        "status": "success" if not errors else "partial",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
