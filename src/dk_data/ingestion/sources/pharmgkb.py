"""PharmGKB loader — inserts chemical rows from bulk TSV download into mol_raw.pharmgkb.

Feature: 019-cms-puf-platform-reconciliation

Each record in records is a flat dict row from chemicals.tsv (one chemical per row).
The row is stored as JSONB in response_body; the pharmgkb_accession_id is used as
the unique request_id to enable idempotent upserts.

Target table: mol_raw.pharmgkb
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4()
    request_id          VARCHAR(100)      — pharmgkb_accession_id
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    api_endpoint        VARCHAR(500)      — "bulk_download/chemicals.tsv"
    api_version         VARCHAR(20)
    request_params      JSONB
    response_status     INTEGER NOT NULL  — always 200 (bulk download)
    response_body       JSONB NOT NULL    — full row as JSONB
    response_body_hash  VARCHAR(64)
    processed_to_bronze BOOLEAN DEFAULT FALSE
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
    source_id           VARCHAR(50) NOT NULL DEFAULT 'pharmgkb'
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "pharmgkb"
BATCH_SIZE = 500


def load_pharmgkb_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load PharmGKB chemical rows into mol_raw.pharmgkb.

    Each element of records is a flat row dict from chemicals.tsv.
    Upserts on pharmgkb_accession_id (ON CONFLICT (request_id) DO UPDATE).

    Args:
        records:     List of row dicts from PharmGKBFetcher.fetch()["records"].
        source_hash: Content hash of the downloaded ZIP for lineage tracking.
        batch_size:  Commit interval.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("PharmGKB loader: no records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_failed": 0,
            "errors": [],
        }

    logger.info("Loading %d PharmGKB chemicals into mol_raw.pharmgkb", len(records))

    inserted = 0
    failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, row in enumerate(records):
                accession_id = row.get("pharmgkb_accession_id") or row.get("pharmgkb accession id")
                if not accession_id:
                    failed += 1
                    errors.append({"index": idx, "error": "missing pharmgkb_accession_id", "type": "validation"})
                    continue

                body_json = json.dumps(row)
                body_hash = hashlib.sha256(body_json.encode()).hexdigest()

                try:
                    cur.execute(
                        """
                        INSERT INTO mol_raw.pharmgkb (
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
                        """,
                        (
                            accession_id,
                            "bulk_download/chemicals.tsv",
                            "v1",
                            json.dumps({"source_hash": source_hash}),
                            200,
                            body_json,
                            body_hash,
                            SOURCE_ID,
                        ),
                    )
                    inserted += 1

                    if inserted % batch_size == 0:
                        conn.commit()
                        logger.debug("PharmGKB: committed %d records", inserted)

                except Exception as exc:
                    failed += 1
                    errors.append({
                        "index": idx,
                        "accession_id": accession_id,
                        "error": str(exc),
                        "type": "database",
                    })
                    logger.error("PharmGKB insert error at index %d: %s", idx, exc)

            conn.commit()

    logger.info("PharmGKB load complete: %d inserted, %d failed", inserted, failed)
    return {
        "status": "success" if inserted > 0 or failed == 0 else "failed",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_failed": failed,
        "errors": errors[:10],
    }
