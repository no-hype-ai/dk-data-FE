"""PBS Australia loader — inserts to mol_raw.pbs_australia.

Loads Australian Pharmaceutical Benefits Scheme schedule records
(from data.pbs.gov.au API or CSV download) into mol_raw.pbs_australia
using ON CONFLICT on request_id (item_code or hash).

Target table: mol_raw.pbs_australia
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_cursor

logger = logging.getLogger(__name__)


def _make_request_id(record: Dict[str, Any]) -> Optional[str]:
    """Build a deterministic request_id from PBS schedule row.

    API JSON uses 'item_code' or 'pbs_code'. CSV rows may use
    'Item Code', 'PBS Code', etc.
    """
    item_code = (
        record.get("item_code")
        or record.get("pbs_code")
        or record.get("Item Code")
        or record.get("PBS Code")
        or record.get("PBS Item Code")
        or record.get("ITEM_CODE")
    )
    if item_code:
        # Include brand/form to disambiguate items with same code
        brand = record.get("brand_name", record.get("Brand Name", ""))
        form = record.get("form", record.get("Form", ""))
        suffix = f"_{brand}_{form}" if brand else ""
        return f"pbs_{item_code}{suffix}"

    # Fallback: hash the entire record
    content = json.dumps(record, sort_keys=True)
    return f"pbs_{hashlib.md5(content.encode()).hexdigest()[:16]}"


def load_pbs_australia_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Load PBS Australia schedule records into mol_raw.pbs_australia.

    Each record is stored as a raw JSONB blob. The Bronze model extracts
    typed fields using JSON path operators.

    Args:
        records: List of PBS schedule dicts from PBSAustraliaFetcher.
        source_hash: Optional content hash; unused but kept for interface consistency.

    Returns:
        Dict with status, records_fetched, records_inserted, errors.
    """
    if not records:
        logger.info("No PBS Australia records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    logger.info(
        "Loading %d PBS Australia records into mol_raw.pbs_australia", len(records)
    )

    errors: List[str] = []
    inserted = 0
    skipped = 0

    sql = """
        INSERT INTO mol_raw.pbs_australia (
            request_id, api_endpoint, api_version,
            response_status, response_body, source_id
        )
        VALUES (%s, 'https://data.pbs.gov.au/api/v3', 'v3', 200, %s::JSONB, 'pbs_australia')
        ON CONFLICT (request_id)
        DO UPDATE SET
            response_body = EXCLUDED.response_body,
            ingested_at   = NOW()
        WHERE mol_raw.pbs_australia.response_body IS DISTINCT FROM EXCLUDED.response_body
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
                    "PBS Australia insert error for %s: %s", request_id, exc
                )

    logger.info(
        "PBS Australia load complete: %d inserted/updated, %d skipped, %d errors",
        inserted, skipped, len(errors),
    )

    return {
        "status": "success" if not errors else "partial",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
