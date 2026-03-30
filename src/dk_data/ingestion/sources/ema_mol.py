"""EMA authorized medicines loader — inserts EPAR rows into mol_raw.ema.

Each record from EMAMolFetcher is a flat dict row from the EPAR product list.
The row is stored as JSONB in response_body; the medicine name + authorisation
date is used to construct a stable request_id for idempotent upserts.

Target table: mol_raw.ema (migration 096, standardised mol_raw schema)
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "ema"
BATCH_SIZE = 500

_SQL = """
    INSERT INTO mol_raw.ema (
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
    WHERE mol_raw.ema.response_body IS DISTINCT FROM EXCLUDED.response_body
"""


def _make_request_id(row: Dict[str, Any]) -> str:
    """Build a stable request_id from the most identifying fields available."""
    # Try authorisation number first (most stable)
    auth_num = (
        row.get("Authorisation number") or row.get("authorisation_number")
        or row.get("EMEA number") or row.get("emea_number")
        or row.get("Product number")
    )
    if auth_num:
        return f"ema_{str(auth_num).strip().replace('/', '_')}"

    # Fall back to medicine name + MA date hash
    name = row.get("Medicine name") or row.get("medicine_name") or row.get("Name") or ""
    date = row.get("Marketing authorisation date") or row.get("First authorised") or ""
    key = f"{name}_{date}".strip().replace(" ", "_")[:80]
    if key:
        return f"ema_{key}"

    # Last resort: hash of full row
    return f"ema_row_{hashlib.md5(json.dumps(row, sort_keys=True).encode()).hexdigest()[:12]}"


def load_ema_mol_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load EMA EPAR product rows into mol_raw.ema.

    Args:
        records:     List of row dicts from EMAMolFetcher.fetch()["records"].
        source_hash: Content hash of the downloaded file for lineage tracking.
        batch_size:  Commit interval.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("EMA mol loader: no records to load")
        return {"status": "success", "records_fetched": 0, "records_inserted": 0, "records_failed": 0, "errors": []}

    logger.info("Loading %d EMA product rows into mol_raw.ema", len(records))

    inserted = 0
    failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, row in enumerate(records):
                request_id = _make_request_id(row)
                body_json = json.dumps(row)
                body_hash = hashlib.sha256(body_json.encode()).hexdigest()

                try:
                    cur.execute(_SQL, (
                        request_id,
                        "bulk_download/epar_product_list",
                        "v1",
                        json.dumps({"source_hash": source_hash}),
                        200,
                        body_json,
                        body_hash,
                        SOURCE_ID,
                    ))
                    inserted += 1

                    if inserted % batch_size == 0:
                        conn.commit()
                        logger.debug("EMA: committed %d records", inserted)

                except Exception as exc:
                    failed += 1
                    errors.append({"index": idx, "request_id": request_id, "error": str(exc), "type": "database"})
                    logger.error("EMA insert error at index %d: %s", idx, exc)

            conn.commit()

    logger.info("EMA mol load complete: %d inserted, %d failed", inserted, failed)
    return {
        "status": "success" if failed == 0 or inserted > 0 else "failed",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_failed": failed,
        "errors": errors[:10],
    }
