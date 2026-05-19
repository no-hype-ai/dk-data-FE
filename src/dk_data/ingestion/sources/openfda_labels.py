"""OpenFDA Drug Labels loader — inserts page blobs into mol_raw.openfda_labels.

Each record from OpenFDALabelsFetcher is a page blob:
    {_request_id, _page_number, results: [...]}

One raw row per page is inserted; the bronze model unnests the results array.
Deduplication uses ON CONFLICT on request_id (unique index created in migration 123).

Target table: mol_raw.openfda_labels (migration 020)
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "openfda_labels"
BATCH_SIZE = 100

_SQL = """
    INSERT INTO mol_raw.openfda_labels (
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
    WHERE mol_raw.openfda_labels.response_body IS DISTINCT FROM EXCLUDED.response_body
"""


def load_openfda_labels_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load OpenFDA drug label page blobs into mol_raw.openfda_labels.

    Args:
        records:     List of page blobs from OpenFDALabelsFetcher.fetch()["records"].
                     Each blob has keys: _request_id, _page_number, results.
        source_hash: Content hash for lineage tracking.
        batch_size:  Commit interval (in pages).

    Returns:
        Dict with status, records_fetched, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("OpenFDA Labels loader: no records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_failed": 0,
            "errors": [],
        }

    logger.info(
        "Loading %d OpenFDA Labels page blobs into mol_raw.openfda_labels", len(records)
    )

    inserted = 0
    failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, page_blob in enumerate(records):
                request_id = page_blob.get(
                    "_request_id", f"fda_labels_unknown_skip{idx * 100:07d}"
                )
                # Strip internal metadata keys before storing
                body = {k: v for k, v in page_blob.items() if not k.startswith("_")}
                body_json = json.dumps(body)
                body_hash = hashlib.sha256(body_json.encode()).hexdigest()
                page_num = page_blob.get("_page_number", idx)

                try:
                    cur.execute(_SQL, (
                        request_id,
                        "https://api.fda.gov/drug/label.json",
                        "v1",
                        json.dumps({
                            "source_hash": source_hash,
                            "page_number": page_num,
                            "label_count": len(body.get("results", [])),
                        }),
                        200,
                        body_json,
                        body_hash,
                        SOURCE_ID,
                    ))
                    inserted += 1

                    if inserted % batch_size == 0:
                        conn.commit()
                        logger.debug(
                            "OpenFDA Labels: committed %d pages", inserted
                        )

                except Exception as exc:
                    failed += 1
                    errors.append({
                        "index": idx,
                        "request_id": request_id,
                        "error": str(exc),
                        "type": "database",
                    })
                    logger.error(
                        "OpenFDA Labels insert error at index %d: %s", idx, exc
                    )

            conn.commit()

    total_labels = sum(
        len(b.get("results", [])) for b in records if not isinstance(b.get("results"), str)
    )
    logger.info(
        "OpenFDA Labels load complete: %d pages inserted (%d labels), %d failed",
        inserted, total_labels, failed,
    )
    return {
        "status": "success" if failed == 0 or inserted > 0 else "failed",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_failed": failed,
        "errors": errors[:10],
    }
