"""ROR research organisations loader — inserts rows into hcp_raw.research_orgs_ror.

Each record from ResearchOrgsRORFetcher is a full ROR v2 organisation object.
The row is stored as JSONB in response_body; the ROR ID is used as
the unique request_id for idempotent upserts.

Target table: hcp_raw.research_orgs_ror (migration 235)
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "research_orgs_ror"
BATCH_SIZE = 500

_SQL = """
    INSERT INTO hcp_raw.research_orgs_ror (
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
    WHERE hcp_raw.research_orgs_ror.response_body IS DISTINCT FROM EXCLUDED.response_body
"""


def _make_request_id(row: Dict[str, Any]) -> str:
    """Build a stable request_id from the ROR ID."""
    ror_id = row.get("id") or row.get("ror_id")
    if ror_id:
        # ROR IDs look like https://ror.org/0abcdef12 — use the suffix
        suffix = str(ror_id).strip().rstrip("/").split("/")[-1]
        return f"ror_{suffix}"

    # Fallback: hash of full record
    return f"ror_row_{hashlib.md5(json.dumps(row, sort_keys=True).encode()).hexdigest()[:12]}"


def load_research_orgs_ror_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load ROR organisation records into hcp_raw.research_orgs_ror.

    Args:
        records:     List of org dicts from ResearchOrgsRORFetcher.fetch()["records"].
        source_hash: Content hash of the downloaded ZIP for lineage tracking.
        batch_size:  Commit interval.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("ROR loader: no records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_failed": 0,
            "errors": [],
        }

    logger.info("Loading %d ROR org records into hcp_raw.research_orgs_ror", len(records))

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
                    cur.execute("SAVEPOINT sp_ror")
                    cur.execute(_SQL, (
                        request_id,
                        "zenodo/ror-data-dump",
                        "v2",
                        json.dumps({"source_hash": source_hash}),
                        200,
                        body_json,
                        body_hash,
                        SOURCE_ID,
                    ))
                    cur.execute("RELEASE SAVEPOINT sp_ror")
                    inserted += 1

                    if inserted % batch_size == 0:
                        conn.commit()
                        logger.debug("ROR: committed %d records", inserted)

                except Exception as exc:
                    cur.execute("ROLLBACK TO SAVEPOINT sp_ror")
                    failed += 1
                    errors.append({
                        "index": idx,
                        "request_id": request_id,
                        "error": str(exc),
                        "type": "database",
                    })
                    logger.error("ROR insert error at index %d: %s", idx, exc)

            conn.commit()

    logger.info("ROR load complete: %d inserted, %d failed", inserted, failed)
    return {
        "status": "success" if inserted > 0 or failed == 0 else "failed",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_failed": failed,
        "errors": errors[:10],
    }
