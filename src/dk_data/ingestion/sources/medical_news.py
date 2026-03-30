"""Medical News Data Loader.

Feature: 011-datasource-integration
Task: T067-T069 — Medical news aggregation

Loads normalised medical news article records into mol_raw.medical_news
with upsert semantics (ON CONFLICT DO UPDATE on article_id).

Target table: mol_raw.medical_news (see migration 060_ci_source_tables.sql)
"""

import logging
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..utils.database import get_connection
from ..utils.validators import MedicalNewsRecord

logger = logging.getLogger(__name__)

# Batch commit interval
BATCH_SIZE = 500


def load_medical_news_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load medical news records into mol_raw.medical_news.

    Validates each record using Pydantic and performs an upsert:
    INSERT ... ON CONFLICT (article_id) DO UPDATE.

    Args:
        records: List of normalised news record dicts from MedicalNewsFetcher.
        source_hash: Optional content hash for lineage tracking.
        source_file: Optional source file identifier.
        batch_size: Number of records to commit at once.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("No medical news records to load")
        return {
            "status": "success",
            "records_inserted": 0,
            "records_failed": 0,
            "errors": [],
        }

    logger.info("Loading %d medical news records into mol_raw.medical_news", len(records))

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(records):
                try:
                    # Validate with Pydantic
                    record = MedicalNewsRecord(**raw_record)

                    cur.execute(
                        """
                        INSERT INTO mol_raw.medical_news (
                            article_id, source_name, title, summary,
                            publication_date, url,
                            drug_mentions, therapeutic_areas,
                            _source_file, _source_hash
                        ) VALUES (
                            %s, %s, %s, %s,
                            %s, %s,
                            %s, %s,
                            %s, %s
                        )
                        ON CONFLICT (article_id) DO UPDATE SET
                            source_name = EXCLUDED.source_name,
                            title = EXCLUDED.title,
                            summary = EXCLUDED.summary,
                            publication_date = EXCLUDED.publication_date,
                            url = EXCLUDED.url,
                            drug_mentions = EXCLUDED.drug_mentions,
                            therapeutic_areas = EXCLUDED.therapeutic_areas,
                            _source_file = EXCLUDED._source_file,
                            _source_hash = EXCLUDED._source_hash,
                            _loaded_at = NOW()
                        """,
                        (
                            record.article_id,
                            record.source_name,
                            record.title,
                            record.summary,
                            record.publication_date,
                            record.url,
                            record.drug_mentions,
                            record.therapeutic_areas,
                            source_file or "medical_news_rss",
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
        "Medical news load complete: %d inserted, %d failed",
        records_inserted, records_failed,
    )

    return {
        "status": "success" if records_inserted > 0 or records_failed == 0 else "failed",
        "records_inserted": records_inserted,
        "records_failed": records_failed,
        "errors": errors[:10],
    }
