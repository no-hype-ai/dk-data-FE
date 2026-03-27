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
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)

SOURCE_ID = "kegg_drug"


def load_kegg_drug_data(conn: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    """Load KEGG Drug batch responses into mol_raw.kegg_drug.

    Each element in ``data["records"]`` is a batch response dict produced by
    KEGGDrugFetcher.  It contains an ``entries`` key with a list of parsed
    KEGG drug dicts.  The full batch dict is stored verbatim as response_body.

    Deduplication is via ON CONFLICT (request_id) DO NOTHING: the request_id
    encodes the batch index and a run timestamp so that re-ingestion of new
    data always inserts, while exact re-delivery of an already-loaded batch
    is silently skipped.

    Args:
        conn: Active psycopg2 connection (caller-managed; this function does
              not open or close the connection).
        data: Output dict from KEGGDrugFetcher.fetch().  Must contain a
              ``"records"`` key with a list of batch response dicts.

    Returns:
        Dict with:
            records_inserted (int): Number of batch rows inserted.
            records_skipped  (int): Number of batch rows skipped (conflict).
    """
    records = data.get("records", [])

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

    with conn.cursor() as cur:
        for batch_num, batch_record in enumerate(records):
            request_id = f"kegg_drug_batch_{batch_num}_{run_ts}"
            response_body_str = json.dumps(batch_record, ensure_ascii=False)

            try:
                cur.execute(sql, (request_id, response_body_str))
                # rowcount == 0 means the ON CONFLICT DO NOTHING path was taken
                if cur.rowcount == 0:
                    skipped += 1
                    logger.debug(
                        "[kegg_drug] Skipped (conflict): request_id=%s", request_id
                    )
                else:
                    inserted += 1
            except Exception as exc:
                logger.error(
                    "[kegg_drug] Insert error for request_id=%s: %s", request_id, exc
                )
                skipped += 1

        conn.commit()

    logger.info(
        "[kegg_drug] Load complete: %d inserted, %d skipped",
        inserted,
        skipped,
    )

    return {"records_inserted": inserted, "records_skipped": skipped}
