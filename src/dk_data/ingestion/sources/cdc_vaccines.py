"""CDC vaccines loader — inserts CVX/MVX codes into mol_raw.cdc_vaccines.

Each record from CDCVaccinesFetcher has a ``_record_type`` key ('cvx', 'mvx',
'cvx_nlm'). The CVX code or MVX code is used as the stable request_id.

Target table: mol_raw.cdc_vaccines (migration 096)
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "cdc_vaccines"
BATCH_SIZE = 500

_SQL = """
    INSERT INTO mol_raw.cdc_vaccines (
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
    WHERE mol_raw.cdc_vaccines.response_body IS DISTINCT FROM EXCLUDED.response_body
"""


def _make_request_id(row: Dict[str, Any]) -> str:
    record_type = row.get("_record_type", "unknown")

    # CVX code (vaccine administered code)
    cvx = row.get("cvx_code") or row.get("cvxCode") or row.get("CVX Code") or row.get("cvx")
    if cvx:
        return f"cdc_{record_type}_{str(cvx).strip()}"

    # MVX code (manufacturer code)
    mvx = row.get("mvx_code") or row.get("mvxCode") or row.get("MVX Code") or row.get("mvx")
    if mvx:
        return f"cdc_{record_type}_{str(mvx).strip()}"

    return f"cdc_{record_type}_{hashlib.md5(json.dumps(row, sort_keys=True).encode()).hexdigest()[:12]}"


def load_cdc_vaccines_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load CDC CVX/MVX vaccine code records into mol_raw.cdc_vaccines.

    Args:
        records:     List of CVX/MVX row dicts from CDCVaccinesFetcher.
        source_hash: Content hash for lineage tracking.
        batch_size:  Commit interval.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("CDCVaccines loader: no records to load")
        return {"status": "success", "records_fetched": 0, "records_inserted": 0, "records_failed": 0, "errors": []}

    logger.info("Loading %d CDC vaccine records into mol_raw.cdc_vaccines", len(records))

    inserted = 0
    failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, row in enumerate(records):
                record_type = row.get("_record_type", "unknown")
                request_id = _make_request_id(row)
                body_json = json.dumps(row)
                body_hash = hashlib.sha256(body_json.encode()).hexdigest()

                try:
                    cur.execute(_SQL, (
                        request_id,
                        f"https://data.cdc.gov/resource/{record_type}.json",
                        "v1",
                        json.dumps({"source_hash": source_hash, "record_type": record_type}),
                        200,
                        body_json,
                        body_hash,
                        SOURCE_ID,
                    ))
                    inserted += 1

                    if inserted % batch_size == 0:
                        conn.commit()
                        logger.debug("CDCVaccines: committed %d records", inserted)

                except Exception as exc:
                    failed += 1
                    errors.append({"index": idx, "request_id": request_id, "error": str(exc), "type": "database"})
                    logger.error("CDCVaccines insert error at index %d: %s", idx, exc)

            conn.commit()

    logger.info("CDCVaccines load complete: %d inserted, %d failed", inserted, failed)
    return {
        "status": "success" if failed == 0 or inserted > 0 else "failed",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_failed": failed,
        "errors": errors[:10],
    }
