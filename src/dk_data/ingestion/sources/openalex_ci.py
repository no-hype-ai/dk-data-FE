"""OpenAlex CI Source Loader.

Feature: 011-datasource-integration
Task: Tier 4 CI source — OpenAlex publications

Loads normalized OpenAlex work records into mol_raw.openalex_ci with
upsert semantics (ON CONFLICT DO UPDATE on work_id).

Table: mol_raw.openalex_ci (see migration 060_ci_source_tables.sql)
"""

import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..utils.database import get_connection
from ..utils.validators import OpenAlexCIRecord

logger = logging.getLogger(__name__)

# Batch commit interval
BATCH_SIZE = 500


def load_openalex_ci_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Load OpenAlex CI records into mol_raw.openalex_ci.

    Validates each record using Pydantic and performs an upsert:
    INSERT ... ON CONFLICT (work_id) DO UPDATE.

    Args:
        records: List of normalized work record dicts from OpenAlexCIFetcher.
        source_hash: Hash of the fetch batch for lineage tracking.

    Returns:
        Dictionary with:
            - status: 'success' or 'failed'
            - records_inserted: number of records upserted
            - records_failed: number of records that failed validation
            - errors: list of first 10 error details
    """
    if not records:
        logger.warning("No OpenAlex CI records to load")
        return {
            "status": "success",
            "records_inserted": 0,
            "records_failed": 0,
            "errors": [],
        }

    logger.info(f"Loading {len(records)} OpenAlex CI records into mol_raw.openalex_ci")

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(records):
                try:
                    # Validate with Pydantic
                    record = OpenAlexCIRecord(**raw_record)

                    # Serialize JSONB fields
                    concepts_json = (
                        json.dumps(record.concepts) if record.concepts is not None else None
                    )
                    authorships_json = (
                        json.dumps(record.authorships) if record.authorships is not None else None
                    )
                    primary_location_json = (
                        json.dumps(record.primary_location)
                        if record.primary_location is not None
                        else None
                    )
                    open_access_json = (
                        json.dumps(record.open_access) if record.open_access is not None else None
                    )

                    cur.execute(
                        """
                        INSERT INTO mol_raw.openalex_ci (
                            work_id, doi, title, abstract, publication_date,
                            cited_by_count, concepts, authorships,
                            primary_location, open_access,
                            _source_file, _source_hash
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s,
                            %s, %s
                        )
                        ON CONFLICT (work_id) DO UPDATE SET
                            doi = EXCLUDED.doi,
                            title = EXCLUDED.title,
                            abstract = EXCLUDED.abstract,
                            publication_date = EXCLUDED.publication_date,
                            cited_by_count = EXCLUDED.cited_by_count,
                            concepts = EXCLUDED.concepts,
                            authorships = EXCLUDED.authorships,
                            primary_location = EXCLUDED.primary_location,
                            open_access = EXCLUDED.open_access,
                            _source_hash = EXCLUDED._source_hash,
                            _loaded_at = NOW()
                        """,
                        (
                            record.work_id,
                            record.doi,
                            record.title,
                            record.abstract,
                            record.publication_date,
                            record.cited_by_count,
                            concepts_json,
                            authorships_json,
                            primary_location_json,
                            open_access_json,
                            "openalex_ci_api",
                            source_hash,
                        ),
                    )
                    records_inserted += 1

                    if records_inserted % BATCH_SIZE == 0:
                        conn.commit()
                        logger.debug(f"Committed batch: {records_inserted} records so far")

                except ValidationError as e:
                    records_failed += 1
                    errors.append({"index": idx, "error": str(e), "type": "validation"})
                    if records_failed <= 5:
                        logger.warning(f"Validation error at index {idx}: {e}")

                except Exception as e:
                    records_failed += 1
                    errors.append({"index": idx, "error": str(e), "type": "database"})
                    logger.error(f"Database error at index {idx}: {e}")

            # Final commit
            conn.commit()

    logger.info(
        f"OpenAlex CI load complete: {records_inserted} upserted, {records_failed} failed"
    )

    return {
        "status": "success" if records_inserted > 0 or records_failed == 0 else "failed",
        "records_inserted": records_inserted,
        "records_failed": records_failed,
        "errors": errors[:10],
    }
