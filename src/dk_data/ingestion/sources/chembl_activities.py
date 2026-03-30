"""ChEMBL Activities loader — inserts activity page blobs into mol_raw.chembl_activities.

Each record from ChEMBLActivitiesFetcher is a page blob:
    {_request_id, _page_number, _offset, activities: [...]}

One raw row per page is inserted; the bronze model unnests the activities array.
Deduplication uses ON CONFLICT on request_id (unique index from migration 126).

Target table: mol_raw.chembl_activities (migration 126)
API endpoint: https://www.ebi.ac.uk/chembl/api/data/activity.json
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "chembl_activities"
BATCH_SIZE = 100

_SQL = """
    INSERT INTO mol_raw.chembl_activities (
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
    WHERE mol_raw.chembl_activities.response_body IS DISTINCT FROM EXCLUDED.response_body
"""


def load_chembl_activities_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load ChEMBL activity page blobs into mol_raw.chembl_activities.

    Args:
        records:     List of page blobs from ChEMBLActivitiesFetcher.fetch()["records"].
                     Each blob has keys: _request_id, _page_number, _offset, activities.
        source_hash: Content hash for lineage tracking.
        batch_size:  Commit interval (in pages).

    Returns:
        Dict with status, records_fetched, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("ChEMBL Activities loader: no records to load")
        return {"status": "success", "records_fetched": 0, "records_inserted": 0,
                "records_failed": 0, "errors": []}

    logger.info("Loading %d ChEMBL activity page blobs into mol_raw.chembl_activities", len(records))

    inserted = 0
    failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, blob in enumerate(records):
                request_id = blob.get("_request_id") or f"chembl_act_{idx}"
                page = blob.get("_page_number", idx)
                offset = blob.get("_offset", 0)

                body = {
                    "activities": blob.get("activities", []),
                    "page_meta": blob.get("page_meta", {}),
                }
                body_json = json.dumps(body, default=str)
                body_hash = hashlib.sha256(body_json.encode()).hexdigest()
                params_json = json.dumps({"page": page, "offset": offset})

                try:
                    cur.execute(_SQL, (
                        request_id,
                        "https://www.ebi.ac.uk/chembl/api/data/activity.json",
                        "v1",
                        params_json,
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
                        errors.append({"index": idx, "request_id": request_id, "error": str(e)[:300]})
                    logger.error("ChEMBL activity page %d failed: %s", page, e)

            conn.commit()

    logger.info("ChEMBL activities load: %d inserted, %d failed", inserted, failed)
    return {
        "status": "success" if failed == 0 else "partial",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_failed": failed,
        "errors": errors,
    }
