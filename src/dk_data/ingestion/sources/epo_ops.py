"""EPO OPS Patent Data Loader.

Feature: 011-datasource-integration
Task: T061-T063 — EPO OPS patent data

Loads normalised EPO patent records into mol_raw.epo_patents with
upsert semantics (ON CONFLICT DO UPDATE on publication_id).

Target table: mol_raw.epo_patents (see migration 060_ci_source_tables.sql)
"""

import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..utils.database import get_connection
from ..utils.validators import EPOPatentRecord

logger = logging.getLogger(__name__)

# Batch commit interval
BATCH_SIZE = 500


def load_epo_ops_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load EPO patent records into mol_raw.epo_patents.

    Validates each record using Pydantic and performs an upsert:
    INSERT ... ON CONFLICT (publication_id) DO UPDATE.

    Args:
        records: List of normalised patent record dicts from EPOOPSFetcher.
        source_hash: Optional content hash for lineage tracking.
        source_file: Optional source file identifier.
        batch_size: Number of records to commit at once.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("No EPO patent records to load")
        return {
            "status": "success",
            "records_inserted": 0,
            "records_failed": 0,
            "errors": [],
        }

    logger.info("Loading %d EPO patent records into mol_raw.epo_patents", len(records))

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(records):
                try:
                    # Validate with Pydantic
                    record = EPOPatentRecord(**raw_record)

                    # Serialize JSONB fields
                    applicants_json = (
                        json.dumps(record.applicants)
                        if record.applicants is not None
                        else None
                    )
                    inventors_json = (
                        json.dumps(record.inventors)
                        if record.inventors is not None
                        else None
                    )

                    cur.execute(
                        """
                        INSERT INTO mol_raw.epo_patents (
                            publication_id, title, abstract,
                            applicants, inventors,
                            filing_date, publication_date,
                            ipc_codes, family_id,
                            _source_file, _source_hash
                        ) VALUES (
                            %s, %s, %s,
                            %s, %s,
                            %s, %s,
                            %s, %s,
                            %s, %s
                        )
                        ON CONFLICT (publication_id) DO UPDATE SET
                            title = EXCLUDED.title,
                            abstract = EXCLUDED.abstract,
                            applicants = EXCLUDED.applicants,
                            inventors = EXCLUDED.inventors,
                            filing_date = EXCLUDED.filing_date,
                            publication_date = EXCLUDED.publication_date,
                            ipc_codes = EXCLUDED.ipc_codes,
                            family_id = EXCLUDED.family_id,
                            _source_file = EXCLUDED._source_file,
                            _source_hash = EXCLUDED._source_hash,
                            _loaded_at = NOW()
                        """,
                        (
                            record.publication_id,
                            record.title,
                            record.abstract,
                            applicants_json,
                            inventors_json,
                            record.filing_date,
                            record.publication_date,
                            record.ipc_codes,
                            record.family_id,
                            source_file or "epo_ops_api",
                            source_hash,
                        ),
                    )
                    records_inserted += 1

                    if records_inserted % batch_size == 0:
                        conn.commit()
                        logger.debug("Committed batch: %d records so far", records_inserted)

                except ValidationError as e:
                    records_failed += 1
                    errors.append({"index": idx, "error": str(e), "type": "validation"})
                    if records_failed <= 5:
                        logger.warning("Validation error at index %d: %s", idx, e)

                except Exception as e:
                    records_failed += 1
                    errors.append({"index": idx, "error": str(e), "type": "database"})
                    logger.error("Database error at index %d: %s", idx, e)

            # Final commit
            conn.commit()

    logger.info(
        "EPO patent load complete: %d inserted, %d failed",
        records_inserted, records_failed,
    )

    return {
        "status": "success" if records_inserted > 0 or records_failed == 0 else "failed",
        "records_inserted": records_inserted,
        "records_failed": records_failed,
        "errors": errors[:10],
    }
