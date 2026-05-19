"""DailyMed SPL loader — inserts drug label metadata into mol_raw.dailymed.

Each record from DailyMedFetcher is a SPL entry dict with set_id, title,
published date, etc. The set_id is used as the stable request_id for upserts.

Target table: mol_raw.dailymed (migration 096)
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "dailymed"
BATCH_SIZE = 500

_SQL = """
    INSERT INTO mol_raw.dailymed (
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
    WHERE mol_raw.dailymed.response_body IS DISTINCT FROM EXCLUDED.response_body
"""


def load_dailymed_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load DailyMed SPL metadata into mol_raw.dailymed.

    Args:
        records:     List of SPL entry dicts from DailyMedFetcher.
        source_hash: Fetch hash for lineage.
        batch_size:  Commit interval.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("DailyMed loader: no records to load")
        return {"status": "success", "records_fetched": 0, "records_inserted": 0, "records_failed": 0, "errors": []}

    logger.info("Loading %d DailyMed SPL records into mol_raw.dailymed", len(records))

    inserted = 0
    failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, row in enumerate(records):
                # set_id is the stable unique identifier for a DailyMed SPL
                set_id = row.get("setid") or row.get("set_id") or row.get("id")
                if not set_id:
                    set_id = f"dailymed_row_{hashlib.md5(json.dumps(row, sort_keys=True).encode()).hexdigest()[:12]}"
                request_id = f"dailymed_{set_id}"
                body_json = json.dumps(row)
                body_hash = hashlib.sha256(body_json.encode()).hexdigest()

                try:
                    cur.execute(_SQL, (
                        request_id,
                        "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json",
                        "v2",
                        json.dumps({"source_hash": source_hash}),
                        200,
                        body_json,
                        body_hash,
                        SOURCE_ID,
                    ))
                    inserted += 1

                    if inserted % batch_size == 0:
                        conn.commit()
                        logger.debug("DailyMed: committed %d records", inserted)

                except Exception as exc:
                    failed += 1
                    errors.append({"index": idx, "set_id": set_id, "error": str(exc), "type": "database"})
                    logger.error("DailyMed insert error at index %d: %s", idx, exc)

            conn.commit()

    logger.info("DailyMed load complete: %d inserted, %d failed", inserted, failed)
    return {
        "status": "success" if failed == 0 or inserted > 0 else "failed",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_failed": failed,
        "errors": errors[:10],
    }
