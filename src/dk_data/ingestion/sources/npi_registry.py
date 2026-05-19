"""NPI Registry loader — inserts to mol_raw.npi_registry.

Loads NPI Registry provider records (raw JSONB from the NPPES API) into
mol_raw.npi_registry using ON CONFLICT on the NPI number expression index.

Target table: mol_raw.npi_registry
Unique index: ON (response_body->>'number') WHERE response_body->>'number' IS NOT NULL
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_cursor

logger = logging.getLogger(__name__)


def load_npi_registry_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Load NPI Registry provider records into mol_raw.npi_registry.

    Each record is stored as a raw JSONB blob. The Bronze model extracts
    typed fields using JSON path operators.

    Deduplication uses ON CONFLICT on the expression index over
    response_body->>'number'. Records without a number (NPI) are skipped.

    Args:
        records: List of raw NPI provider dicts from NPIRegistryFetcher.
        source_hash: Optional content hash; unused but kept for interface consistency.

    Returns:
        Dict with status, records_fetched, records_inserted, errors.
    """
    if not records:
        logger.info("No NPI Registry records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    logger.info(
        "Loading %d NPI Registry records into mol_raw.npi_registry", len(records)
    )

    errors: List[str] = []
    inserted = 0
    skipped = 0

    sql = """
        INSERT INTO mol_raw.npi_registry (
            response_body, source_id
        )
        VALUES (%s::JSONB, 'npi_registry')
        ON CONFLICT ((response_body->>'number'))
        WHERE (response_body->>'number') IS NOT NULL
        DO UPDATE SET
            response_body = EXCLUDED.response_body,
            ingested_at   = NOW()
        WHERE mol_raw.npi_registry.response_body IS DISTINCT FROM EXCLUDED.response_body
    """

    with get_cursor() as cur:
        for record in records:
            npi = record.get("number")
            if not npi:
                skipped += 1
                continue
            try:
                cur.execute("SAVEPOINT sp")
                cur.execute(sql, (json.dumps(record),))
                cur.execute("RELEASE SAVEPOINT sp")
                inserted += 1
            except Exception as exc:
                cur.execute("ROLLBACK TO SAVEPOINT sp")
                errors.append(f"npi={npi}: {exc}")
                logger.warning("NPI Registry insert error for npi=%s: %s", npi, exc)

    logger.info(
        "NPI Registry load complete: %d inserted/updated, %d skipped (no npi), %d errors",
        inserted, skipped, len(errors),
    )

    return {
        "status": "success" if not errors else "partial",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
