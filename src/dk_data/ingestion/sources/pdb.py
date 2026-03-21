"""PDB structure data loader.

Feature: 012-platform-hardening (US3)

Loads PDB structure records into raw.pdb with upsert semantics.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..utils.database import get_connection
from ..utils.validators import PDBRecord

logger = logging.getLogger(__name__)


def load_pdb_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load PDB structure records into raw.pdb.

    Args:
        records: Structure records from PDBFetcher.fetch().
        source_hash: Content hash for tracking.
        source_file: Source file identifier.
        batch_size: Commit batch size.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.info("No PDB records to load")
        return {"status": "success", "records_inserted": 0, "records_failed": 0}

    logger.info(f"Loading {len(records)} PDB records into raw.pdb")

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(records):
                try:
                    validated = PDBRecord(
                        pdb_id=raw_record.get("pdb_id", ""),
                        title=raw_record.get("title"),
                        method=raw_record.get("method"),
                        resolution=raw_record.get("resolution"),
                        deposit_date=raw_record.get("deposit_date"),
                    )

                    cur.execute(
                        """
                        INSERT INTO mol_raw.pdb (
                            pdb_id, title, method, resolution,
                            deposit_date, raw_response,
                            _source_file, _source_hash
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (pdb_id) DO UPDATE SET
                            title = EXCLUDED.title,
                            method = EXCLUDED.method,
                            resolution = EXCLUDED.resolution,
                            deposit_date = EXCLUDED.deposit_date,
                            raw_response = EXCLUDED.raw_response,
                            _loaded_at = NOW(),
                            _source_file = EXCLUDED._source_file,
                            _source_hash = EXCLUDED._source_hash
                        """,
                        (
                            validated.pdb_id, validated.title,
                            validated.method, validated.resolution,
                            validated.deposit_date,
                            json.dumps(raw_record.get("raw_response", {})),
                            source_file, source_hash,
                        ),
                    )
                    records_inserted += 1

                    if records_inserted % batch_size == 0:
                        conn.commit()

                except (ValidationError, Exception) as e:
                    records_failed += 1
                    errors.append({"index": idx, "pdb_id": raw_record.get("pdb_id"), "error": str(e)})
                    if records_failed <= 10:
                        logger.warning(f"Error at index {idx}: {e}")

            conn.commit()

    logger.info(f"PDB load complete: {records_inserted} inserted, {records_failed} failed")
    return {
        "status": "success" if records_failed == 0 else "partial",
        "records_inserted": records_inserted,
        "records_failed": records_failed,
        "errors": errors[:10] if errors else [],
    }
