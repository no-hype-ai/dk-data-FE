"""PubChem loader — inserts to mol_raw.pubchem.

Loads PubChem compound records (raw JSONB from the SDQ API) into
mol_raw.pubchem using ON CONFLICT on the cid expression index.

Target table: mol_raw.pubchem
Unique index: ON (response_body->>'cid') WHERE response_body->>'cid' IS NOT NULL
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_cursor

logger = logging.getLogger(__name__)


def load_pubchem_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Load PubChem compound records into mol_raw.pubchem.

    Each record is stored as a raw JSONB blob. The Bronze model extracts
    typed fields using JSON path operators.

    Deduplication uses ON CONFLICT on the expression index over
    response_body->>'cid'. Records without a cid are skipped.

    Args:
        records: List of raw PubChem compound dicts from PubChemFetcher.
        source_hash: Optional content hash; unused but kept for interface consistency.

    Returns:
        Dict with status, records_fetched, records_inserted, errors.
    """
    if not records:
        logger.info("No PubChem records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    logger.info("Loading %d PubChem records into mol_raw.pubchem", len(records))

    errors: List[str] = []
    inserted = 0
    skipped = 0

    sql = """
        INSERT INTO mol_raw.pubchem (response_body, source_id)
        VALUES (%s::JSONB, 'pubchem')
        ON CONFLICT ((response_body->>'cid'))
        WHERE (response_body->>'cid') IS NOT NULL
        DO UPDATE SET
            response_body = EXCLUDED.response_body,
            ingested_at   = NOW()
        WHERE mol_raw.pubchem.response_body IS DISTINCT FROM EXCLUDED.response_body
    """

    with get_cursor() as cur:
        for record in records:
            cid = record.get("cid") or record.get("CID")
            if not cid:
                skipped += 1
                continue
            # Normalise key to lowercase 'cid' for consistent expression index
            if "CID" in record and "cid" not in record:
                record = dict(record)
                record["cid"] = record.pop("CID")
            try:
                cur.execute(sql, (json.dumps(record),))
                inserted += 1
            except Exception as exc:
                errors.append(f"cid={cid}: {exc}")
                logger.warning("PubChem insert error for cid=%s: %s", cid, exc)

    logger.info(
        "PubChem load complete: %d inserted/updated, %d skipped (no cid), %d errors",
        inserted, skipped, len(errors),
    )

    return {
        "status": "success" if not errors else "partial",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
