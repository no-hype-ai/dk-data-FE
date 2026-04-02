"""EuropePMC loader — inserts to mol_raw.europepmc.

Feature: 011-datasource-integration
Task: EuropePMC literature source integration

Loads EuropePMC search result records (raw JSONB from the /search API)
into mol_raw.europepmc using ON CONFLICT on the pmid expression index.

Target table: mol_raw.europepmc (see migration 085_cms_puf_platform_reconciliation.sql)
Schema:
    id                  BIGSERIAL PRIMARY KEY
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    response_status     INTEGER NOT NULL DEFAULT 200
    response_body       JSONB NOT NULL        -- raw EuropePMC search result object
    processed_to_bronze BOOLEAN NOT NULL DEFAULT FALSE
    _loaded_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()

Unique index: ON (response_body->>'pmid') WHERE response_body->>'pmid' IS NOT NULL
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_cursor

logger = logging.getLogger(__name__)


def load_europepmc_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Load EuropePMC search result records into mol_raw.europepmc.

    Each record is stored as a raw JSONB blob (the search result object from
    the EuropePMC REST API).  The Bronze model (bronze.europepmc) extracts
    typed fields from response_body using JSON path operators.

    Deduplication uses ON CONFLICT on the expression index over
    response_body->>'pmid'.  Records without a pmid are skipped.

    Args:
        records: List of raw EuropePMC API result dicts from EuropePMCFetcher.
        source_hash: Optional content hash; unused but kept for interface consistency.

    Returns:
        Dict with status, records_fetched, records_inserted, errors.
    """
    if not records:
        logger.info("No EuropePMC records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    logger.info("Loading %d EuropePMC records into mol_raw.europepmc", len(records))

    errors: List[str] = []
    inserted = 0
    skipped = 0

    # ON CONFLICT uses the expression index; PostgreSQL requires the exact
    # expression (response_body->>'pmid') in the conflict target.
    sql = """
        INSERT INTO mol_raw.europepmc (response_body, response_status)
        VALUES (%s::JSONB, 200)
        ON CONFLICT ((response_body->>'pmid'))
        WHERE (response_body->>'pmid') IS NOT NULL
        DO UPDATE SET
            response_body = EXCLUDED.response_body,
            _loaded_at    = NOW()
        WHERE mol_raw.europepmc.response_body IS DISTINCT FROM EXCLUDED.response_body
    """

    with get_cursor() as cur:
        for record in records:
            pmid = record.get("pmid")
            if not pmid:
                skipped += 1
                continue
            try:
                cur.execute(sql, (json.dumps(record),))
                inserted += 1
            except Exception as exc:
                errors.append(f"pmid={pmid}: {exc}")
                logger.warning("EuropePMC insert error for pmid=%s: %s", pmid, exc)

    logger.info(
        "EuropePMC load complete: %d inserted/updated, %d skipped (no pmid), %d errors",
        inserted, skipped, len(errors),
    )

    return {
        "status": "success" if not errors else "partial",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
