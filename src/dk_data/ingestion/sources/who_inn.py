"""WHO INN loader — inserts to mol_raw.who_inn.

Feature: 019-cms-puf-platform-reconciliation

Loads PubChem synonyms API responses (InformationList format) for WHO
International Nonproprietary Names into mol_raw.who_inn.

Target table: mol_raw.who_inn
  (migration 095 moves raw.who_inn → mol_raw.who_inn)

request_id format: who_inn_pubchem_{cid_or_name}_{YYYYMMDDHHMMSS}
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..utils.database import get_cursor

logger = logging.getLogger(__name__)

_TIMESTAMP_FMT = "%Y%m%d%H%M%S"
BATCH_SIZE = 200
SOURCE_ID = "who_inn"

_SQL = """
    INSERT INTO mol_raw.who_inn (
        request_id,
        response_status,
        response_body,
        response_body_hash,
        source_id
    )
    VALUES (%s, 200, %s::JSONB, %s, %s)
    ON CONFLICT (request_id)
    DO UPDATE SET
        response_body      = EXCLUDED.response_body,
        response_body_hash = EXCLUDED.response_body_hash,
        processed_to_bronze = FALSE,
        ingested_at        = NOW()
    WHERE mol_raw.who_inn.response_body IS DISTINCT FROM EXCLUDED.response_body
"""


def _body_hash(record: Dict[str, Any]) -> str:
    return hashlib.md5(json.dumps(record, sort_keys=True).encode()).hexdigest()


def _extract_cid_or_name(record: Dict[str, Any]) -> Optional[str]:
    """Extract dedup key: PubChem CID > queried name > None."""
    info_list = record.get("InformationList", {}).get("Information", [])
    if info_list:
        cid = info_list[0].get("CID")
        if cid is not None:
            return str(cid)
    queried = record.get("_queried_name")
    if queried:
        return queried.strip().lower().replace(" ", "_").replace("/", "_")
    return None


def load_who_inn_data(
    conn: Any,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """Load WHO INN PubChem synonym records into mol_raw.who_inn.

    Args:
        conn: Unused — loader opens its own cursor via get_cursor().
        data: Result from WHOINNFetcher.fetch().

    Returns:
        {"records_inserted": int, "records_skipped": int}
    """
    records: List[Dict[str, Any]] = data.get("records", [])
    if not records:
        logger.info("No WHO INN records to load")
        return {"records_inserted": 0, "records_skipped": 0}

    logger.info("Loading %d WHO INN records into mol_raw.who_inn", len(records))

    timestamp = datetime.now(timezone.utc).strftime(_TIMESTAMP_FMT)
    inserted = 0
    skipped = 0

    for batch_start in range(0, len(records), BATCH_SIZE):
        batch = records[batch_start : batch_start + BATCH_SIZE]
        with get_cursor() as cur:
            for record in batch:
                cid_or_name = _extract_cid_or_name(record)
                if not cid_or_name:
                    skipped += 1
                    continue

                request_id = f"who_inn_pubchem_{cid_or_name}_{timestamp}"
                body_hash = _body_hash(record)

                try:
                    cur.execute(_SQL, (request_id, json.dumps(record), body_hash, SOURCE_ID))
                    inserted += 1
                except Exception as exc:
                    logger.warning("WHO INN insert error for %s: %s", request_id, exc)
                    skipped += 1

    logger.info(
        "WHO INN load complete: %d inserted, %d skipped", inserted, skipped
    )
    return {"records_inserted": inserted, "records_skipped": skipped}
