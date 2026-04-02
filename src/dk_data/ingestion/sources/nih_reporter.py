"""NIH Reporter loader — inserts to mol_raw.nih_reporter.

Feature: 019-cms-puf-platform-reconciliation

Table schema (085_cms_puf_platform_reconciliation.sql):
    id                  BIGSERIAL PRIMARY KEY
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    response_status     INTEGER NOT NULL DEFAULT 200
    response_body       JSONB NOT NULL
    processed_to_bronze BOOLEAN NOT NULL DEFAULT FALSE
    _loaded_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()

Unique index: ON (response_body->>'project_num') WHERE project_num IS NOT NULL
ON CONFLICT: DO NOTHING (idempotent re-ingestion of same project_num)

The loader writes the full raw API response dict as JSONB. The bronze SQLMesh model
(mol_bronze.nih_reporter) extracts typed columns from response_body.
"""
import json
import logging
from typing import List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

BATCH_SIZE = 500  # commit every N records to bound transaction size


def load_nih_reporter_data(records: list, source_hash: Optional[str] = None) -> dict:
    """
    Load NIH Reporter project records into mol_raw.nih_reporter.

    Args:
        records: List of raw API response dicts from NIHReporterFetcher.
                 Each dict must contain 'project_num' or 'project_number'.
        source_hash: Unused; kept for interface consistency.

    Returns:
        Standard result dict:
            status: "success" | "partial"
            records_fetched: int
            records_inserted: int
            records_updated: int  (always 0 — DO NOTHING on conflict)
            errors: list of error strings (capped at 10)
    """
    if not records:
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    errors: List[str] = []
    inserted = 0

    sql = """
        INSERT INTO mol_raw.nih_reporter (response_body, response_status)
        VALUES (%s::jsonb, 200)
        ON CONFLICT ((response_body->>'project_num'))
        WHERE (response_body->>'project_num') IS NOT NULL
        DO NOTHING
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            for batch_start in range(0, len(records), BATCH_SIZE):
                batch = records[batch_start:batch_start + BATCH_SIZE]
                for r in batch:
                    project_num = r.get("project_num") or r.get("project_number")
                    if not project_num:
                        continue
                    try:
                        cur.execute(sql, (json.dumps(r),))
                        inserted += 1
                    except Exception as e:
                        error_msg = f"project_num={project_num}: {e}"
                        errors.append(error_msg)
                        if len(errors) <= 10:
                            logger.warning(f"NIH Reporter insert error: {error_msg}")
                        # Rollback this cursor state and re-open
                        conn.rollback()
                        cur = conn.cursor()
                conn.commit()

    logger.info(
        "NIH Reporter load complete: %d inserted from %d fetched records"
        " (%d errors)",
        inserted, len(records), len(errors),
    )

    return {
        "status": "success" if not errors else "partial",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
