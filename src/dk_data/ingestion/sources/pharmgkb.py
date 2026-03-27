"""PharmGKB loader — inserts paged API responses to mol_raw.pharmgkb.

Feature: 019-cms-puf-platform-reconciliation

Each record in data["records"] is a full page response dict from
PharmGKBFetcher (one page = one row in mol_raw.pharmgkb).

Target table: mol_raw.pharmgkb
Schema (matches raw.pharmgkb defined in migration 062, promoted to mol_raw):
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4()
    request_id          VARCHAR(100) NOT NULL
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    api_endpoint        VARCHAR(500) NOT NULL
    api_version         VARCHAR(20)
    request_params      JSONB
    response_status     INTEGER NOT NULL
    response_body       JSONB NOT NULL
    response_body_hash  VARCHAR(64)
    processed_to_bronze BOOLEAN DEFAULT FALSE
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
    source_id           VARCHAR(50) NOT NULL DEFAULT 'pharmgkb'

Deduplication: ON CONFLICT (request_id) DO NOTHING — idempotent for the same
page + entity_type + timestamp combination.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)

SOURCE_ID = "pharmgkb"
TABLE = "mol_raw.pharmgkb"
BASE_URL = "https://api.pharmgkb.org/v1"

_INSERT_SQL = """
    INSERT INTO mol_raw.pharmgkb (
        request_id,
        api_endpoint,
        api_version,
        request_params,
        response_status,
        response_body,
        response_body_hash,
        source_id
    )
    VALUES (
        %(request_id)s,
        %(api_endpoint)s,
        %(api_version)s,
        %(request_params)s::jsonb,
        %(response_status)s,
        %(response_body)s::jsonb,
        %(response_body_hash)s,
        %(source_id)s
    )
    ON CONFLICT (request_id) DO NOTHING
"""


def load_pharmgkb_data(conn: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    """Load PharmGKB page responses into mol_raw.pharmgkb.

    Each element of data["records"] is a raw page response dict produced by
    PharmGKBFetcher.  One page = one row.  The request_id encodes the entity
    type, page number, and a UTC timestamp so that incremental re-runs are
    idempotent (DO NOTHING on conflict).

    Args:
        conn:  psycopg2 database connection (caller-managed lifecycle).
        data:  Result dict from PharmGKBFetcher.fetch(), expected keys:
                   records     — list of page response dicts
                   entity_type — "chemical" or "gene" (optional, default "chemical")
                   hash        — content hash (optional, unused)

    Returns:
        Dict with:
            records_inserted: int
            records_skipped:  int
    """
    records = data.get("records", [])
    entity_type: str = data.get("entity_type", "chemical")

    if not records:
        logger.info("PharmGKB loader: no records to insert")
        return {"records_inserted": 0, "records_skipped": 0}

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    inserted = 0
    skipped = 0

    with conn.cursor() as cur:
        for page in records:
            page_num: int = page.get("_page_num", 0)
            request_id = f"pharmgkb_{entity_type}_page_{page_num}_{timestamp}"

            # Serialise the full page response as the stored JSONB blob
            body_json = json.dumps(page)
            body_hash = hashlib.sha256(body_json.encode()).hexdigest()

            api_endpoint = (
                f"{BASE_URL}/data/{entity_type}"
                f"?view=max&pageSize=100&page={page_num}"
            )
            request_params = json.dumps(
                {"view": "max", "pageSize": 100, "page": page_num}
            )

            try:
                cur.execute(
                    _INSERT_SQL,
                    {
                        "request_id": request_id,
                        "api_endpoint": api_endpoint,
                        "api_version": "v1",
                        "request_params": request_params,
                        "response_status": 200,
                        "response_body": body_json,
                        "response_body_hash": body_hash,
                        "source_id": SOURCE_ID,
                    },
                )
                # rowcount 0 means DO NOTHING fired (duplicate request_id)
                if cur.rowcount == 0:
                    skipped += 1
                    logger.debug(
                        "PharmGKB page %d (%s) already present — skipped",
                        page_num, entity_type,
                    )
                else:
                    inserted += 1
            except Exception as exc:
                logger.warning(
                    "PharmGKB insert error for %s page %d: %s",
                    entity_type, page_num, exc,
                )
                conn.rollback()
                skipped += 1
                continue

        conn.commit()

    logger.info(
        "PharmGKB load complete: %d inserted, %d skipped (entity_type=%s)",
        inserted, skipped, entity_type,
    )
    return {"records_inserted": inserted, "records_skipped": skipped}
