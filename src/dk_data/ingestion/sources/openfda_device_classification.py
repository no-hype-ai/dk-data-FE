"""OpenFDA Device Classification loader — inserts page blobs into
dev_raw.openfda_device_classification.

Target table: dev_raw.openfda_device_classification (migration 248)
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "openfda_device_classification"
BATCH_SIZE = 100

_SQL = """
    INSERT INTO dev_raw.openfda_device_classification (
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
        response_body      = EXCLUDED.response_body,
        response_body_hash = EXCLUDED.response_body_hash,
        ingested_at        = NOW()
    WHERE dev_raw.openfda_device_classification.response_body IS DISTINCT FROM EXCLUDED.response_body
"""


def load_openfda_device_classification_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load OpenFDA Device Classification page blobs into raw."""
    if not records:
        logger.warning("OpenFDA Classification loader: no records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_failed": 0,
            "errors": [],
        }

    logger.info(
        "Loading %d OpenFDA Classification page blobs", len(records)
    )

    inserted = 0
    failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, page_blob in enumerate(records):
                request_id = page_blob.get(
                    "_request_id",
                    f"fda_device_classification_unknown_skip{idx * 100:07d}",
                )
                body = {k: v for k, v in page_blob.items() if not k.startswith("_")}
                body_json = json.dumps(body)
                body_hash = hashlib.sha256(body_json.encode()).hexdigest()
                page_num = page_blob.get("_page_number", idx)

                try:
                    cur.execute(_SQL, (
                        request_id,
                        "https://api.fda.gov/device/classification.json",
                        "v1",
                        json.dumps({
                            "source_hash": source_hash,
                            "page_number": page_num,
                            "record_count": len(body.get("results", [])),
                        }),
                        200,
                        body_json,
                        body_hash,
                        SOURCE_ID,
                    ))
                    inserted += 1

                    if inserted % batch_size == 0:
                        conn.commit()

                except Exception as exc:
                    failed += 1
                    errors.append({
                        "index": idx,
                        "request_id": request_id,
                        "error": str(exc),
                        "type": "database",
                    })
                    logger.error(
                        "OpenFDA Classification insert error at index %d: %s", idx, exc
                    )

            conn.commit()

    total_records = sum(
        len(b.get("results", [])) for b in records if not isinstance(b.get("results"), str)
    )
    logger.info(
        "OpenFDA Classification load complete: %d pages (%d classification records), %d failed",
        inserted, total_records, failed,
    )
    return {
        "status": "success" if failed == 0 or inserted > 0 else "failed",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_failed": failed,
        "errors": errors[:10],
    }
