"""ChEMBL Molecules loader — inserts to mol_raw.chembl.

Loads ChEMBL molecule records (raw JSONB from the /molecule API) into
mol_raw.chembl using ON CONFLICT on the molecule_chembl_id expression index.

Target table: mol_raw.chembl
Unique index: ON (response_body->>'molecule_chembl_id')
              WHERE response_body->>'molecule_chembl_id' IS NOT NULL
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_cursor

logger = logging.getLogger(__name__)


def load_chembl_molecules_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Load ChEMBL molecule records into mol_raw.chembl.

    Each record is stored as a raw JSONB blob. The Bronze model extracts
    typed fields using JSON path operators.

    Deduplication uses ON CONFLICT on the expression index over
    response_body->>'molecule_chembl_id'. Records without a molecule_chembl_id
    are skipped.

    Args:
        records: List of raw ChEMBL molecule dicts from ChEMBLMoleculesFetcher.
        source_hash: Optional content hash; unused but kept for interface consistency.

    Returns:
        Dict with status, records_fetched, records_inserted, errors.
    """
    if not records:
        logger.info("No ChEMBL molecule records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    logger.info("Loading %d ChEMBL molecule records into mol_raw.chembl", len(records))

    errors: List[str] = []
    inserted = 0
    skipped = 0

    sql = """
        INSERT INTO mol_raw.chembl (response_body, source_id)
        VALUES (%s::JSONB, 'chembl_molecules')
        ON CONFLICT ((response_body->>'molecule_chembl_id'))
        WHERE (response_body->>'molecule_chembl_id') IS NOT NULL
        DO UPDATE SET
            response_body = EXCLUDED.response_body,
            ingested_at   = NOW()
        WHERE mol_raw.chembl.response_body IS DISTINCT FROM EXCLUDED.response_body
    """

    with get_cursor() as cur:
        for record in records:
            chembl_id = record.get("molecule_chembl_id")
            if not chembl_id:
                skipped += 1
                continue
            try:
                cur.execute(sql, (json.dumps(record),))
                inserted += 1
            except Exception as exc:
                errors.append(f"molecule_chembl_id={chembl_id}: {exc}")
                logger.warning(
                    "ChEMBL insert error for molecule_chembl_id=%s: %s",
                    chembl_id, exc,
                )

    logger.info(
        "ChEMBL load complete: %d inserted/updated, %d skipped (no id), %d errors",
        inserted, skipped, len(errors),
    )

    return {
        "status": "success" if not errors else "partial",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
