"""FDA REMS loader — inserts REMS application records into mol_raw.fda_rems.

Source: OpenFDA drug/drugsfda endpoint filtered for REMS submissions.
Each record is an NDA/ANDA/BLA application dict that has at least one
submission with submission_type == 'REMS'.

application_number is used as the stable request_id.

Target table: mol_raw.fda_rems (migration 126)
API endpoint: https://api.fda.gov/drug/drugsfda.json
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "fda_rems"
BATCH_SIZE = 200

_SQL = """
    INSERT INTO mol_raw.fda_rems (
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
    WHERE mol_raw.fda_rems.response_body IS DISTINCT FROM EXCLUDED.response_body
"""


def load_fda_rems_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load FDA REMS application records into mol_raw.fda_rems.

    Args:
        records:     List of application dicts from FDARemsFetcher.
                     Each dict represents an NDA/ANDA/BLA application with REMS submissions.
        source_hash: Content hash for lineage tracking.
        batch_size:  Commit interval.

    Returns:
        Dict with status, records_fetched, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("FDA REMS loader: no records to load")
        return {"status": "success", "records_fetched": 0, "records_inserted": 0,
                "records_failed": 0, "errors": []}

    logger.info("Loading %d FDA REMS records into mol_raw.fda_rems", len(records))

    inserted = 0
    failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, row in enumerate(records):
                app_no = row.get("application_number") or f"rems_row_{idx}"
                request_id = f"fda_rems_{str(app_no).strip().replace('/', '_')}"
                body_json = json.dumps(row, default=str)
                body_hash = hashlib.sha256(body_json.encode()).hexdigest()

                try:
                    cur.execute(_SQL, (
                        request_id,
                        "https://api.fda.gov/drug/drugsfda.json",
                        "v1",
                        json.dumps({"application_number": app_no}),
                        200,
                        body_json,
                        body_hash,
                        SOURCE_ID,
                    ))
                    inserted += 1

                    if inserted % batch_size == 0:
                        conn.commit()

                except Exception as e:
                    failed += 1
                    if len(errors) < 10:
                        errors.append({"index": idx, "application_number": app_no, "error": str(e)[:300]})
                    logger.error("FDA REMS record %s failed: %s", app_no, e)

            conn.commit()

    logger.info("FDA REMS load: %d inserted, %d failed", inserted, failed)
    return {
        "status": "success" if failed == 0 else "partial",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_failed": failed,
        "errors": errors,
    }
