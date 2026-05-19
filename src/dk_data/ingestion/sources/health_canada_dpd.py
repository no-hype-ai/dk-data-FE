"""Health Canada DPD loader — inserts rows into mol_raw.health_canada_dpd.

Each record from HealthCanadaDPDFetcher is a flat dict row from one of the
pipe-delimited TXT files in the DPD ZIP. The _dpd_file tag identifies which
file the row came from (drug_product, active_ingredient, company, etc.).

The row is stored as JSONB in response_body; a stable request_id is derived
from the drug_code + _dpd_file combination for idempotent upserts.

Target table: mol_raw.health_canada_dpd (migration 235)
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "health_canada_dpd"
BATCH_SIZE = 500

_SQL = """
    INSERT INTO mol_raw.health_canada_dpd (
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
    WHERE mol_raw.health_canada_dpd.response_body IS DISTINCT FROM EXCLUDED.response_body
"""


def _make_request_id(row: Dict[str, Any]) -> str:
    """Build a stable request_id from DPD identifying fields."""
    dpd_file = row.get("_dpd_file", "unknown")
    drug_code = row.get("drug_code") or row.get("drug_identification_number")

    if drug_code:
        # For files with sub-keys (ingredients, routes, etc.) include a hash
        # to differentiate multiple rows with the same drug_code
        row_hash = hashlib.md5(json.dumps(row, sort_keys=True).encode()).hexdigest()[:8]
        return f"dpd_{dpd_file}_{str(drug_code).strip()}_{row_hash}"

    # Fallback: hash of full row
    return f"dpd_{dpd_file}_{hashlib.md5(json.dumps(row, sort_keys=True).encode()).hexdigest()[:12]}"


def load_health_canada_dpd_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load Health Canada DPD rows into mol_raw.health_canada_dpd.

    Args:
        records:     List of row dicts from HealthCanadaDPDFetcher.fetch()["records"].
        source_hash: Content hash of the downloaded ZIP for lineage tracking.
        batch_size:  Commit interval.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("Health Canada DPD loader: no records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_failed": 0,
            "errors": [],
        }

    logger.info("Loading %d Health Canada DPD rows into mol_raw.health_canada_dpd", len(records))

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
                    cur.execute("SAVEPOINT sp_dpd")
                    cur.execute(_SQL, (
                        request_id,
                        f"bulk_download/dpd_{row.get('_dpd_file', 'unknown')}",
                        "v1",
                        json.dumps({"source_hash": source_hash}),
                        200,
                        body_json,
                        body_hash,
                        SOURCE_ID,
                    ))
                    cur.execute("RELEASE SAVEPOINT sp_dpd")
                    inserted += 1

                    if inserted % batch_size == 0:
                        conn.commit()
                        logger.debug("DPD: committed %d records", inserted)

                except Exception as exc:
                    cur.execute("ROLLBACK TO SAVEPOINT sp_dpd")
                    failed += 1
                    errors.append({
                        "index": idx,
                        "request_id": request_id,
                        "error": str(exc),
                        "type": "database",
                    })
                    logger.error("DPD insert error at index %d: %s", idx, exc)

            conn.commit()

    logger.info("DPD load complete: %d inserted, %d failed", inserted, failed)
    return {
        "status": "success" if inserted > 0 or failed == 0 else "failed",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_failed": failed,
        "errors": errors[:10],
    }
