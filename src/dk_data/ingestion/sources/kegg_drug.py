"""KEGG Drug loader — inserts to mol_raw.kegg_drug.

Feature: 019-cms-puf-platform-reconciliation

Loads KEGG Drug batch responses (raw JSONB from the /get endpoint) into
mol_raw.kegg_drug using the standard JSONB envelope pattern.

Each record from KEGGDrugFetcher.fetch()["records"] is a batch response dict
with an ``entries`` key containing a list of parsed KEGG drug dicts.  The
entire batch response is stored as response_body JSONB; one DB row per batch.

Target table: mol_raw.kegg_drug
Expected schema (JSONB envelope):
    id                  BIGSERIAL PRIMARY KEY
    request_id          TEXT NOT NULL
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    response_status     INTEGER NOT NULL DEFAULT 200
    response_body       JSONB NOT NULL
    processed_to_bronze BOOLEAN NOT NULL DEFAULT FALSE
    _loaded_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()

Deduplication: ON CONFLICT (request_id) DO NOTHING — batch request IDs
encode source + batch index + timestamp, so re-ingestion of a new run
creates new rows while a true duplicate (same request_id) is skipped.
"""

import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "kegg_drug"


def load_kegg_drug_data(
    records_or_conn: Any,
    data: Any = None,
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Load KEGG Drug batch responses into mol_raw.kegg_drug.

    Supports both calling conventions:
      New (orchestrator): load_kegg_drug_data(records_list, source_hash=hash)
      Old: load_kegg_drug_data(conn, data_dict)

    Returns:
        Dict with records_inserted (int) and records_skipped (int).
    """
    # Detect calling convention
    if isinstance(records_or_conn, list):
        records: List[Any] = records_or_conn
        _own_conn = True
    else:
        # Old convention: records_or_conn is an open psycopg2 connection
        records = (data or {}).get("records", []) if data else []
        _own_conn = False

    if not records:
        logger.info("[kegg_drug] No records to load")
        return {"records_inserted": 0, "records_skipped": 0}

    logger.info("[kegg_drug] Loading %d batch records into mol_raw.kegg_drug", len(records))

    # Use a single timestamp for the entire run so all batches share the
    # same run identifier component in their request_id.
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    sql = """
        INSERT INTO mol_raw.kegg_drug (
            request_id,
            request_timestamp,
            response_status,
            response_body,
            processed_to_bronze,
            _loaded_at
        ) VALUES (
            %s,
            NOW(),
            200,
            %s::JSONB,
            FALSE,
            NOW()
        )
        ON CONFLICT (request_id) DO NOTHING
    """

    inserted = 0
    skipped = 0

    def _run(cur: Any) -> None:
        nonlocal inserted, skipped
        for batch_num, batch_record in enumerate(records):
            request_id = f"kegg_drug_batch_{batch_num}_{run_ts}"
            response_body_str = json.dumps(batch_record, ensure_ascii=False)
            try:
                cur.execute(sql, (request_id, response_body_str))
                if cur.rowcount == 0:
                    skipped += 1
                    logger.debug("[kegg_drug] Skipped (conflict): request_id=%s", request_id)
                else:
                    inserted += 1
            except Exception as exc:
                logger.error("[kegg_drug] Insert error for request_id=%s: %s", request_id, exc)
                skipped += 1

    if _own_conn:
        with get_connection() as conn_obj:
            with conn_obj.cursor() as cur:
                _run(cur)
            conn_obj.commit()
    else:
        with records_or_conn.cursor() as cur:
            _run(cur)
        records_or_conn.commit()

    logger.info(
        "[kegg_drug] Load complete: %d inserted, %d skipped",
        inserted,
        skipped,
    )

    return {"records_inserted": inserted, "records_skipped": skipped}
