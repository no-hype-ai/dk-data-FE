"""FDA Orange Book loader — inserts products/patents/exclusivity into mol_raw.orange_book.

Each record dict from OrangeBookFetcher has a ``_file_type`` key
('products', 'patents', 'exclusivity'). Records are upserted into
mol_raw.orange_book with a stable request_id derived from application
number + file type.

Target table: mol_raw.orange_book (migration 096)
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "orange_book"
BATCH_SIZE = 500

_SQL = """
    INSERT INTO mol_raw.orange_book (
        request_id,
        api_endpoint,
        api_version,
        request_params,
        response_status,
        response_body,
        response_body_hash,
        source_id
    ) VALUES (
        %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s
    )
    ON CONFLICT (request_id) DO UPDATE SET
        response_body       = EXCLUDED.response_body,
        response_body_hash  = EXCLUDED.response_body_hash,
        ingested_at         = NOW()
    WHERE mol_raw.orange_book.response_body IS DISTINCT FROM EXCLUDED.response_body
"""


def _make_request_id(row: Dict[str, Any]) -> str:
    """Build a stable request_id from application number + file type."""
    file_type = row.get("_file_type", "unknown")

    # Products file key fields
    appl_no = (
        row.get("Appl_No") or row.get("APPL_NO") or row.get("appl_no")
        or row.get("New Drug Application (NDA) Number")
    )
    if appl_no:
        product_no = row.get("Product_No") or row.get("PRODUCT_NO") or ""
        return f"ob_{file_type}_{str(appl_no).strip()}_{str(product_no).strip()}"

    # Patents/exclusivity key
    pat_no = row.get("Patent_No") or row.get("Exclusivity_Code") or ""
    if appl_no and pat_no:
        return f"ob_{file_type}_{appl_no}_{str(pat_no).strip()[:20]}"

    return f"ob_{file_type}_{hashlib.md5(json.dumps(row, sort_keys=True).encode()).hexdigest()[:12]}"


def load_orange_book_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load FDA Orange Book records into mol_raw.orange_book.

    Args:
        records:     List of row dicts from OrangeBookFetcher.fetch()["records"].
        source_hash: Content hash for lineage tracking.
        batch_size:  Commit interval.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("OrangeBook loader: no records to load")
        return {"status": "success", "records_fetched": 0, "records_inserted": 0, "records_failed": 0, "errors": []}

    logger.info("Loading %d Orange Book records into mol_raw.orange_book", len(records))

    inserted = 0
    failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, row in enumerate(records):
                file_type = row.get("_file_type", "unknown")
                request_id = _make_request_id(row)
                body_json = json.dumps(row)
                body_hash = hashlib.sha256(body_json.encode()).hexdigest()

                try:
                    cur.execute(_SQL, (
                        request_id,
                        f"bulk_download/orange_book_{file_type}",
                        "v1",
                        json.dumps({"source_hash": source_hash, "file_type": file_type}),
                        200,
                        body_json,
                        body_hash,
                        SOURCE_ID,
                    ))
                    inserted += 1

                    if inserted % batch_size == 0:
                        conn.commit()
                        logger.debug("OrangeBook: committed %d records", inserted)

                except Exception as exc:
                    failed += 1
                    errors.append({"index": idx, "request_id": request_id, "error": str(exc), "type": "database"})
                    logger.error("OrangeBook insert error at index %d: %s", idx, exc)

            conn.commit()

    logger.info("OrangeBook load complete: %d inserted, %d failed", inserted, failed)
    return {
        "status": "success" if failed == 0 or inserted > 0 else "failed",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_failed": failed,
        "errors": errors[:10],
    }
