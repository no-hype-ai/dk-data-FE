"""DrugBank Data Loader.

Feature: 011-datasource-integration
Task: Phase 6 / US4 — credential-gated source (DrugBank)

Loads validated DrugBank drug records into raw.drugbank with
upsert semantics (ON CONFLICT DO UPDATE on drugbank_id).

Target table: raw.drugbank (see migration 063_drugbank_raw_table.sql)
"""

import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..utils.database import get_connection
from ..utils.validators import DrugBankRecord

logger = logging.getLogger(__name__)

# Batch commit interval
BATCH_SIZE = 500


def load_drugbank_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load DrugBank records into raw.drugbank.

    Validates each record using Pydantic and performs an upsert:
    INSERT ... ON CONFLICT (drugbank_id) DO UPDATE.

    Args:
        records: List of normalized drug record dicts from DrugBankFetcher.
        source_hash: Hash of the fetch batch for lineage tracking.
        source_file: Source file identifier.
        batch_size: Number of records to commit at once.

    Returns:
        Dictionary with:
            - status: 'success' or 'failed'
            - records_inserted: number of records upserted
            - records_failed: number of records that failed validation
            - errors: list of first 10 error details
    """
    if not records:
        logger.warning("No DrugBank records to load")
        return {
            "status": "success",
            "records_inserted": 0,
            "records_failed": 0,
            "errors": [],
        }

    logger.info("Loading %d DrugBank records into raw.drugbank", len(records))

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(records):
                try:
                    # Validate with Pydantic
                    record = DrugBankRecord(**raw_record)

                    # Serialize JSONB fields
                    targets_json = (
                        json.dumps(record.targets)
                        if record.targets is not None
                        else None
                    )
                    enzymes_json = (
                        json.dumps(record.enzymes)
                        if record.enzymes is not None
                        else None
                    )

                    cur.execute(
                        """
                        INSERT INTO mol_raw.drugbank (
                            drugbank_id, name, description, cas_number,
                            categories, targets, enzymes,
                            indication, pharmacodynamics,
                            _source_file, _source_hash
                        ) VALUES (
                            %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s,
                            %s, %s
                        )
                        ON CONFLICT (drugbank_id) DO UPDATE SET
                            name = EXCLUDED.name,
                            description = EXCLUDED.description,
                            cas_number = EXCLUDED.cas_number,
                            categories = EXCLUDED.categories,
                            targets = EXCLUDED.targets,
                            enzymes = EXCLUDED.enzymes,
                            indication = EXCLUDED.indication,
                            pharmacodynamics = EXCLUDED.pharmacodynamics,
                            _source_file = EXCLUDED._source_file,
                            _source_hash = EXCLUDED._source_hash,
                            _loaded_at = NOW()
                        """,
                        (
                            record.drugbank_id,
                            record.name,
                            record.description,
                            record.cas_number,
                            record.categories if record.categories else None,
                            targets_json,
                            enzymes_json,
                            record.indication,
                            record.pharmacodynamics,
                            source_file or "drugbank_xml",
                            source_hash,
                        ),
                    )
                    records_inserted += 1

                    if records_inserted % batch_size == 0:
                        conn.commit()
                        logger.debug("Committed batch: %d records so far", records_inserted)

                except ValidationError as e:
                    records_failed += 1
                    errors.append({
                        "index": idx,
                        "drugbank_id": raw_record.get("drugbank_id"),
                        "error": str(e),
                        "type": "validation",
                    })
                    if records_failed <= 5:
                        logger.warning(
                            "Validation error at index %d: %s", idx, e
                        )

                except Exception as e:
                    records_failed += 1
                    errors.append({
                        "index": idx,
                        "drugbank_id": raw_record.get("drugbank_id"),
                        "error": str(e),
                        "type": "database",
                    })
                    logger.error("Database error at index %d: %s", idx, e)

            # Final commit
            conn.commit()

    logger.info(
        "DrugBank load complete: %d upserted, %d failed",
        records_inserted,
        records_failed,
    )

    return {
        "status": "success" if records_inserted > 0 or records_failed == 0 else "failed",
        "records_inserted": records_inserted,
        "records_failed": records_failed,
        "errors": errors[:10],
    }
