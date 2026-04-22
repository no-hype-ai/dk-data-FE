"""Shared JSONB-page-blob loader for all TGA sources.

All 5 Tier-A TGA sources share the standard mol_raw / dev_raw JSONB pattern:
one raw row per fetcher page blob with ON CONFLICT (request_id) idempotent upsert.

This helper avoids copy-pasting near-identical loader code 5 times.
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

BATCH_SIZE = 100


def load_tga_page_blobs(
    records: List[Dict[str, Any]],
    *,
    table: str,                 # fully-qualified, e.g. 'mol_raw.tga_artg_medicines'
    source_id: str,             # value for source_id column
    api_endpoint: str,          # e.g. 'https://apps.tga.gov.au/prod/MSI/search'
    source_hash: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load a list of TGA page blobs into the specified raw table.

    Each page blob must carry:
      - _request_id: stable id per page (fetcher responsibility)
      - _page_number: int (for logging)
      - results: list of records OR a dict describing the payload

    Returns dict with status, records_fetched, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("TGA loader (%s): no records to load", source_id)
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_failed": 0,
            "errors": [],
        }

    sql = f"""
        INSERT INTO {table} (
            request_id,
            api_endpoint,
            api_version,
            request_params,
            response_status,
            response_body,
            response_body_hash,
            source_id
        ) VALUES (%s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s)
        ON CONFLICT (request_id) DO UPDATE SET
            response_body      = EXCLUDED.response_body,
            response_body_hash = EXCLUDED.response_body_hash,
            ingested_at        = NOW()
        WHERE {table}.response_body IS DISTINCT FROM EXCLUDED.response_body
    """

    logger.info(
        "Loading %d TGA page blobs into %s (source=%s)",
        len(records), table, source_id,
    )

    inserted = 0
    failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, page_blob in enumerate(records):
                request_id = page_blob.get("_request_id", f"{source_id}_unknown_{idx:07d}")
                body = {k: v for k, v in page_blob.items() if not k.startswith("_")}
                body_json = json.dumps(body, default=str)
                body_hash = hashlib.sha256(body_json.encode()).hexdigest()
                page_num = page_blob.get("_page_number", idx)

                try:
                    cur.execute(sql, (
                        request_id,
                        api_endpoint,
                        "v1",
                        json.dumps({
                            "source_hash": source_hash,
                            "page_number": page_num,
                            "record_count": len(body.get("results", [])) if isinstance(body.get("results"), list) else 1,
                        }),
                        200,
                        body_json,
                        body_hash,
                        source_id,
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
                    logger.error("TGA loader (%s) insert error idx=%d: %s", source_id, idx, exc)

            conn.commit()

    logger.info(
        "TGA loader (%s) complete: %d inserted, %d failed",
        source_id, inserted, failed,
    )
    return {
        "status": "success" if failed == 0 or inserted > 0 else "failed",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_failed": failed,
        "errors": errors[:10],
    }
