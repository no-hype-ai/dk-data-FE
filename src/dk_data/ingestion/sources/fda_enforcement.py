"""FDA Enforcement loader — inserts page blobs into mol_raw.fda_enforcement.

Each record from FDAEnforcementFetcher is a page blob:
    {_request_id, _page_number, results: [...]}

One raw row per page is inserted; the bronze model unnests the results array.
Deduplication uses ON CONFLICT on response_body_hash (MD5 of page content).

Target table: mol_raw.fda_enforcement
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_cursor

logger = logging.getLogger(__name__)

SOURCE_ID = "fda_enforcement"
_API_ENDPOINT = "https://api.fda.gov/drug/enforcement.json"

_SQL = """
    INSERT INTO mol_raw.fda_enforcement
        (request_id, api_endpoint, response_status, response_body, response_body_hash, source_id)
    VALUES (%s, %s, %s, %s::JSONB, %s, %s)
    ON CONFLICT (response_body_hash) DO NOTHING
"""


def load_fda_enforcement_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Load FDA enforcement page blobs into mol_raw.fda_enforcement.

    Each record is a page blob containing a ``results`` array of enforcement
    reports. The Bronze model unnests results via
    ``jsonb_array_elements(response_body->'results')``.

    Deduplication uses response_body_hash to avoid re-inserting identical pages.

    Args:
        records: List of page blobs from FDAEnforcementFetcher (each has
            a ``results`` key with a list of enforcement report dicts).
        source_hash: Optional content hash; unused but kept for interface consistency.

    Returns:
        Dict with status, records_fetched, records_inserted, errors.
    """
    if not records:
        logger.info("No FDA enforcement records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    logger.info(
        "Loading %d FDA enforcement page blobs into mol_raw.fda_enforcement",
        len(records),
    )

    errors: List[str] = []
    inserted = 0

    with get_cursor() as cur:
        for page_blob in records:
            body_json = json.dumps(page_blob)
            body_hash = hashlib.md5(body_json.encode()).hexdigest()
            request_id = page_blob.get("_request_id") or (
                f"enforcement_page_{page_blob.get('_page_number', 0)}"
            )
            try:
                cur.execute(_SQL, (
                    request_id,
                    _API_ENDPOINT,
                    200,
                    body_json,
                    body_hash,
                    SOURCE_ID,
                ))
                inserted += 1
            except Exception as exc:
                errors.append(f"request_id={request_id}: {exc}")
                logger.warning(
                    "FDA enforcement insert error for request_id=%s: %s",
                    request_id,
                    exc,
                )

    logger.info(
        "FDA enforcement load complete: %d inserted, %d errors",
        inserted,
        len(errors),
    )

    return {
        "status": "success" if not errors else "partial",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
