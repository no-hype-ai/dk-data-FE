"""RxNorm loader — inserts to mol_raw.rxnorm.

Feature: 019-cms-puf-platform-reconciliation

Loads raw NLM RxNorm API responses produced by RxNormFetcher into
mol_raw.rxnorm using ON CONFLICT on request_id.

Target table: mol_raw.rxnorm (see migration 089_entity_linking_gaps.sql)
Schema:
    id                  BIGSERIAL PRIMARY KEY
    request_id          TEXT NOT NULL UNIQUE      -- deterministic dedup key
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    response_status     INTEGER NOT NULL DEFAULT 200
    response_body       JSONB NOT NULL            -- raw API response object
    response_body_hash  TEXT                      -- MD5 of serialised body
    processed_to_bronze BOOLEAN NOT NULL DEFAULT FALSE
    _loaded_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()

Deduplication: ON CONFLICT (request_id) — UPDATE only when the body has
changed (response_body IS DISTINCT FROM EXCLUDED.response_body).

request_id format:
  bulk concepts  — rxnorm_concepts_{tty}_{YYYYMMDDHHMMSS}  e.g. rxnorm_concepts_IN_20260327120000
  properties     — rxnorm_prop_{rxcui}_{YYYYMMDDHHMMSS}    e.g. rxnorm_prop_1049502_20260327120000
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..utils.database import get_cursor

logger = logging.getLogger(__name__)

_TIMESTAMP_FMT = "%Y%m%d%H%M%S"


def _body_hash(record: Dict[str, Any]) -> str:
    """Compute an MD5 hex digest of the serialised record."""
    return hashlib.md5(json.dumps(record, sort_keys=True).encode()).hexdigest()


def _is_bulk_record(record: Dict[str, Any]) -> bool:
    """Return True when the record came from the bulk allconcepts endpoint."""
    return "_tty" in record


def _build_request_id(record: Dict[str, Any], timestamp: str) -> str:
    """Build the deterministic request_id for a record."""
    if _is_bulk_record(record):
        tty = record.get("_tty", "UNKNOWN")
        return f"rxnorm_concepts_{tty}_{timestamp}"
    rxcui = record.get("_rxcui", "UNKNOWN")
    return f"rxnorm_prop_{rxcui}_{timestamp}"


_SQL = """
    INSERT INTO mol_raw.rxnorm (
        request_id,
        response_status,
        response_body,
        response_body_hash
    )
    VALUES (%s, 200, %s::JSONB, %s)
    ON CONFLICT (request_id)
    DO UPDATE SET
        response_body      = EXCLUDED.response_body,
        response_body_hash = EXCLUDED.response_body_hash,
        _loaded_at         = NOW()
    WHERE mol_raw.rxnorm.response_body IS DISTINCT FROM EXCLUDED.response_body
"""


def load_rxnorm_data(conn: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    """Load RxNorm API response records into mol_raw.rxnorm.

    Each entry in ``data["records"]`` is a raw API response dict produced by
    RxNormFetcher.  The function builds a deterministic ``request_id`` for
    each record, then upserts it — skipping silently when the body is
    unchanged.

    Args:
        conn: A psycopg2 connection.  Passed for interface consistency; the
              function uses the shared ``get_cursor()`` pool context manager
              rather than the supplied connection so that it integrates
              cleanly with the rest of the ingestion layer.
        data: Dict as returned by ``RxNormFetcher.fetch()``, expected to
              contain a ``"records"`` key with a list of API response dicts.

    Returns:
        Dict with keys:
            records_inserted — number of rows inserted or updated
            records_skipped  — number of rows skipped (no change / empty)
    """
    records: List[Dict[str, Any]] = data.get("records", [])

    if not records:
        logger.info("No RxNorm records to load")
        return {"records_inserted": 0, "records_skipped": 0}

    logger.info("Loading %d RxNorm records into mol_raw.rxnorm", len(records))

    # Single timestamp for this batch so bulk records get stable, predictable
    # request_ids within a run but don't collide across runs.
    timestamp = datetime.now(timezone.utc).strftime(_TIMESTAMP_FMT)

    inserted = 0
    skipped = 0

    with get_cursor() as cur:
        for record in records:
            if not record:
                skipped += 1
                continue

            request_id = _build_request_id(record, timestamp)
            body_json = json.dumps(record)
            body_hash = _body_hash(record)

            try:
                cur.execute(_SQL, (request_id, body_json, body_hash))
                # rowcount == 1 means INSERT or UPDATE fired; 0 means the
                # ON CONFLICT … WHERE clause suppressed the update (no change)
                if cur.rowcount and cur.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
            except Exception as exc:
                logger.warning(
                    "RxNorm insert error for request_id=%s: %s", request_id, exc
                )
                skipped += 1

    logger.info(
        "RxNorm load complete: %d inserted/updated, %d skipped",
        inserted,
        skipped,
    )
    return {"records_inserted": inserted, "records_skipped": skipped}
