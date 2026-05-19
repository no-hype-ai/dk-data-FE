"""FDA Drugs@FDA loader — inserts NDA/ANDA/BLA records into mol_raw.fda_drugs.

Each record from FDADrugsFetcher is an application dict from the OpenFDA
drugsfda.json API. The application_number is used as the stable request_id.

Target table: mol_raw.fda_drugs (migration 096)
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "fda_drugs"
BATCH_SIZE = 500

_SQL = """
    INSERT INTO mol_raw.fda_drugs (
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
    WHERE mol_raw.fda_drugs.response_body IS DISTINCT FROM EXCLUDED.response_body
"""


def load_fda_drugs_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load FDA Drugs@FDA application records into mol_raw.fda_drugs.

    Args:
        records:     List of application dicts from FDADrugsFetcher.
        source_hash: Fetch hash for lineage.
        batch_size:  Commit interval.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("FDADrugs loader: no records to load")
        return {"status": "success", "records_fetched": 0, "records_inserted": 0, "records_failed": 0, "errors": []}

    logger.info("Loading %d FDA Drugs records into mol_raw.fda_drugs", len(records))

    inserted = 0
    failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, row in enumerate(records):
                app_no = row.get("application_number") or row.get("openfda", {}).get("application_number", [""])[0]
                if not app_no:
                    app_no = f"fda_row_{hashlib.md5(json.dumps(row, sort_keys=True).encode()).hexdigest()[:12]}"
                request_id = f"fda_drugs_{str(app_no).strip().replace('/', '_')}"
                body_json = json.dumps(row)
                body_hash = hashlib.sha256(body_json.encode()).hexdigest()

                try:
                    cur.execute(_SQL, (
                        request_id,
                        "https://api.fda.gov/drug/drugsfda.json",
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
                        logger.debug("FDADrugs: committed %d records", inserted)

                except Exception as exc:
                    failed += 1
                    errors.append({"index": idx, "app_no": app_no, "error": str(exc), "type": "database"})
                    logger.error("FDADrugs insert error at index %d: %s", idx, exc)

            conn.commit()

    logger.info("FDADrugs load complete: %d inserted, %d failed", inserted, failed)
    return {
        "status": "success" if failed == 0 or inserted > 0 else "failed",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_failed": failed,
        "errors": errors[:10],
    }
