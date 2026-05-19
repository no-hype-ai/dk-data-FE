"""OpenFDA FAERS loader — inserts to mol_raw.openfda_faers.

Loads FAERS adverse event page blobs (raw JSONB from the /drug/event API)
into mol_raw.openfda_faers. Each row represents one API page containing a
``results`` array of event reports.

Target table: mol_raw.openfda_faers
Dedup: response_body_hash (MD5 of page content to avoid duplicate page ingestion)
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_cursor

logger = logging.getLogger(__name__)


def load_openfda_faers_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Load OpenFDA FAERS page blobs into mol_raw.openfda_faers.

    Each record is a page blob containing a ``results`` array of adverse
    event reports. The Bronze model unnests results via
    ``jsonb_array_elements(response_body->'results')``.

    Deduplication uses response_body_hash to avoid re-inserting identical
    pages. New pages (incremental or backfill runs) are always inserted.

    Args:
        records: List of page blobs from OpenFDAFAERSFetcher (each has
            a ``results`` key with a list of event report dicts).
        source_hash: Optional content hash; unused but kept for interface consistency.

    Returns:
        Dict with status, records_fetched, records_inserted, errors.
    """
    if not records:
        logger.info("No OpenFDA FAERS records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    logger.info(
        "Loading %d OpenFDA FAERS page blobs into mol_raw.openfda_faers", len(records)
    )

    errors: List[str] = []
    inserted = 0

    sql = """
        INSERT INTO mol_raw.openfda_faers
            (request_id, api_endpoint, response_status, response_body, response_body_hash, source_id)
        VALUES (%s, %s, %s, %s::JSONB, %s, 'openfda_faers')
        ON CONFLICT (response_body_hash) DO NOTHING
    """
    _API_ENDPOINT = "https://api.fda.gov/drug/event.json"

    with get_cursor() as cur:
        for page_blob in records:
            body_json = json.dumps(page_blob)
            body_hash = hashlib.md5(body_json.encode()).hexdigest()
            request_id = page_blob.get("_request_id") or f"faers_page_{page_blob.get('_page_number', 0)}"
            try:
                cur.execute(sql, (request_id, _API_ENDPOINT, 200, body_json, body_hash))
                inserted += 1
            except Exception as exc:
                request_id = page_blob.get("_request_id", "unknown")
                errors.append(f"request_id={request_id}: {exc}")
                logger.warning(
                    "OpenFDA FAERS insert error for request_id=%s: %s",
                    request_id, exc,
                )

    logger.info(
        "OpenFDA FAERS load complete: %d inserted, %d errors",
        inserted, len(errors),
    )

    return {
        "status": "success" if not errors else "partial",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
