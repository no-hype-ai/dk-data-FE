"""TTD loader — inserts Therapeutic Target Database records into mol_raw.ttd.

Each record from TTDFetcher has a ``_file_type`` and ``_id`` field.
The combination of file_type + _id is used as the stable request_id.

Target table: mol_raw.ttd (migration 096)
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "ttd"
BATCH_SIZE = 500

_SQL = """
    INSERT INTO mol_raw.ttd (
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
    WHERE mol_raw.ttd.response_body IS DISTINCT FROM EXCLUDED.response_body
"""


def load_ttd_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load TTD flat-file records into mol_raw.ttd.

    Args:
        records:     List of record dicts from TTDFetcher.
        source_hash: Content hash for lineage tracking.
        batch_size:  Commit interval.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("TTD loader: no records to load")
        return {"status": "success", "records_fetched": 0, "records_inserted": 0, "records_failed": 0, "errors": []}

    logger.info("Loading %d TTD records into mol_raw.ttd", len(records))

    inserted = 0
    failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, row in enumerate(records):
                file_type = row.get("_file_type", "unknown")
                entity_id = row.get("_id", "")
                if entity_id:
                    request_id = f"ttd_{file_type}_{str(entity_id).strip()}"
                else:
                    request_id = f"ttd_{file_type}_{hashlib.md5(json.dumps(row, sort_keys=True).encode()).hexdigest()[:12]}"

                body_json = json.dumps(row)
                body_hash = hashlib.sha256(body_json.encode()).hexdigest()

                try:
                    cur.execute(_SQL, (
                        request_id,
                        f"bulk_download/ttd_{file_type}",
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
                        logger.debug("TTD: committed %d records", inserted)

                except Exception as exc:
                    failed += 1
                    errors.append({"index": idx, "request_id": request_id, "error": str(exc), "type": "database"})
                    logger.error("TTD insert error at index %d: %s", idx, exc)

            conn.commit()

    logger.info("TTD load complete: %d inserted, %d failed", inserted, failed)
    return {
        "status": "success" if failed == 0 or inserted > 0 else "failed",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_failed": failed,
        "errors": errors[:10],
    }
