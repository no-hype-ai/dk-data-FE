"""EMA EPAR assessment reports loader — inserts rows into mol_raw.ema_epar.

Each record from EMAEparFetcher is a flat dict row from the EPAR CSV.
The row is stored as JSONB in response_body; a stable request_id is
derived from the product/procedure number for idempotent upserts.

Target table: mol_raw.ema_epar (migration 235)
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "ema_epar"
BATCH_SIZE = 500

_SQL = """
    INSERT INTO mol_raw.ema_epar (
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
    WHERE mol_raw.ema_epar.response_body IS DISTINCT FROM EXCLUDED.response_body
"""


def _make_request_id(row: Dict[str, Any]) -> str:
    """Build a stable request_id from EPAR identifying fields."""
    # Try product/procedure number first
    proc_num = (
        row.get("product_number")
        or row.get("ema_product_number")
        or row.get("procedure_number")
        or row.get("authorisation_number")
    )
    if proc_num:
        return f"epar_{str(proc_num).strip().replace('/', '_')}"

    # Fall back to medicine name hash
    name = row.get("medicine_name") or row.get("name_of_medicine") or ""
    if name:
        return f"epar_{name.strip().replace(' ', '_')[:60]}"

    # Last resort: hash of full row
    return f"epar_row_{hashlib.md5(json.dumps(row, sort_keys=True).encode()).hexdigest()[:12]}"


def load_ema_epar_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load EMA EPAR assessment report rows into mol_raw.ema_epar.

    Args:
        records:     List of row dicts from EMAEparFetcher.fetch()["records"].
        source_hash: Content hash of the downloaded file for lineage tracking.
        batch_size:  Commit interval.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("EMA EPAR loader: no records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_failed": 0,
            "errors": [],
        }

    logger.info("Loading %d EMA EPAR rows into mol_raw.ema_epar", len(records))

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
                    cur.execute("SAVEPOINT sp_epar")
                    cur.execute(_SQL, (
                        request_id,
                        "bulk_download/epar_csv",
                        "v1",
                        json.dumps({"source_hash": source_hash}),
                        200,
                        body_json,
                        body_hash,
                        SOURCE_ID,
                    ))
                    cur.execute("RELEASE SAVEPOINT sp_epar")
                    inserted += 1

                    if inserted % batch_size == 0:
                        conn.commit()
                        logger.debug("EMA EPAR: committed %d records", inserted)

                except Exception as exc:
                    cur.execute("ROLLBACK TO SAVEPOINT sp_epar")
                    failed += 1
                    errors.append({
                        "index": idx,
                        "request_id": request_id,
                        "error": str(exc),
                        "type": "database",
                    })
                    logger.error("EMA EPAR insert error at index %d: %s", idx, exc)

            conn.commit()

    logger.info("EMA EPAR load complete: %d inserted, %d failed", inserted, failed)
    return {
        "status": "success" if inserted > 0 or failed == 0 else "failed",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_failed": failed,
        "errors": errors[:10],
    }
