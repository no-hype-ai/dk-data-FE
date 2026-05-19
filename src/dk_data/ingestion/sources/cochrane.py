"""Cochrane Systematic Reviews Data Loader.

Feature: 011-datasource-integration
Task: T064-T066 — Cochrane systematic reviews

Loads normalised Cochrane review records into mol_raw.cochrane_reviews
with upsert semantics (ON CONFLICT DO UPDATE on review_id).

Target table: mol_raw.cochrane_reviews (see migration 060_ci_source_tables.sql)
"""

import logging
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..utils.database import get_connection
from ..utils.validators import CochraneReviewRecord

logger = logging.getLogger(__name__)

# Batch commit interval
BATCH_SIZE = 500


def load_cochrane_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load Cochrane review records into mol_raw.cochrane_reviews.

    Validates each record using Pydantic and performs an upsert:
    INSERT ... ON CONFLICT (review_id) DO UPDATE.

    Args:
        records: List of normalised review record dicts from CochraneFetcher.
        source_hash: Optional content hash for lineage tracking.
        source_file: Optional source file identifier.
        batch_size: Number of records to commit at once.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("No Cochrane review records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    logger.info("Loading %d Cochrane review records into mol_raw.cochrane_reviews", len(records))

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(records):
                try:
                    # Validate with Pydantic
                    record = CochraneReviewRecord(**raw_record)

                    cur.execute(
                        """
                        INSERT INTO mol_raw.cochrane_reviews (
                            review_id, pmid, title, authors, abstract,
                            publication_date, review_type,
                            interventions, conditions,
                            conclusions, doi,
                            _source_file, _source_hash
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s,
                            %s, %s,
                            %s, %s,
                            %s, %s
                        )
                        ON CONFLICT (review_id) DO UPDATE SET
                            pmid = EXCLUDED.pmid,
                            title = EXCLUDED.title,
                            authors = EXCLUDED.authors,
                            abstract = EXCLUDED.abstract,
                            publication_date = EXCLUDED.publication_date,
                            review_type = EXCLUDED.review_type,
                            interventions = EXCLUDED.interventions,
                            conditions = EXCLUDED.conditions,
                            conclusions = EXCLUDED.conclusions,
                            doi = EXCLUDED.doi,
                            _source_file = EXCLUDED._source_file,
                            _source_hash = EXCLUDED._source_hash,
                            _loaded_at = NOW()
                        """,
                        (
                            record.review_id,
                            record.pmid,
                            record.title,
                            record.authors,
                            record.abstract,
                            record.publication_date,
                            record.review_type,
                            record.interventions,
                            record.conditions,
                            record.conclusions,
                            record.doi,
                            source_file or "cochrane_api",
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
        "Cochrane review load complete: %d inserted, %d failed",
        records_inserted, records_failed,
    )

    return {
        "status": "success" if records_inserted > 0 or records_failed == 0 else "failed",
        "records_fetched": len(records),
        "records_inserted": records_inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
