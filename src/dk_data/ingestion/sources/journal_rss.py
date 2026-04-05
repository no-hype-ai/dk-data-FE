"""Journal RSS Data Loader.

Feature: 011-datasource-integration
Task: T051-T054 — Journal RSS CI source integration

Loads normalized journal RSS article records into mol_raw.journal_rss
with upsert semantics (ON CONFLICT DO UPDATE on article_id).

Target table: mol_raw.journal_rss (see migration 060_ci_source_tables.sql)
"""

import json
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..utils.database import get_connection
from ..utils.validators import JournalRSSRecord

logger = logging.getLogger(__name__)

# Batch commit interval
BATCH_SIZE = 500


def load_journal_rss_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load journal RSS article records into mol_raw.journal_rss.

    Validates each record via the JournalRSSRecord Pydantic model and
    performs an upsert: INSERT ... ON CONFLICT (article_id) DO UPDATE.

    Args:
        records: List of article record dicts from JournalRSSFetcher.
        source_hash: Optional content hash for tracking.
        source_file: Optional source file identifier.
        batch_size: Number of records to commit at once.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.info("No journal RSS records to load")
        return {
            "status": "success",
            "records_inserted": 0,
            "records_failed": 0,
            "errors": [],
        }

    logger.info("Loading %d journal RSS records into mol_raw.journal_rss", len(records))

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(records):
                try:
                    cur.execute("SAVEPOINT sp_record")
                    # Validate via Pydantic model
                    validated = JournalRSSRecord(
                        article_id=raw_record.get("article_id", ""),
                        feed_source=raw_record.get("feed_source", ""),
                        title=raw_record.get("title"),
                        authors=raw_record.get("authors"),
                        abstract=raw_record.get("abstract"),
                        publication_date=_parse_date(
                            raw_record.get("publication_date")
                        ),
                        link=raw_record.get("link"),
                        doi=raw_record.get("doi"),
                        categories=raw_record.get("categories"),
                    )

                    # authors and categories are JSONB columns — serialize Python values to JSON
                    authors_json = (
                        json.dumps(validated.authors) if validated.authors is not None else None
                    )
                    categories_json = (
                        json.dumps(validated.categories) if validated.categories else None
                    )

                    cur.execute(
                        """
                        INSERT INTO mol_raw.journal_rss (
                            article_id, feed_source, title, authors,
                            abstract, publication_date, link, doi,
                            categories,
                            _source_file, _source_hash
                        ) VALUES (
                            %s, %s, %s, %s::JSONB,
                            %s, %s, %s, %s,
                            %s::JSONB,
                            %s, %s
                        )
                        ON CONFLICT (article_id) DO UPDATE SET
                            feed_source = EXCLUDED.feed_source,
                            title = EXCLUDED.title,
                            authors = EXCLUDED.authors,
                            abstract = EXCLUDED.abstract,
                            publication_date = EXCLUDED.publication_date,
                            link = EXCLUDED.link,
                            doi = EXCLUDED.doi,
                            categories = EXCLUDED.categories,
                            _source_file = EXCLUDED._source_file,
                            _source_hash = EXCLUDED._source_hash,
                            _loaded_at = NOW()
                        """,
                        (
                            validated.article_id,
                            validated.feed_source,
                            validated.title,
                            authors_json,
                            validated.abstract,
                            validated.publication_date,
                            validated.link,
                            validated.doi,
                            categories_json,
                            source_file or "journal_rss_feed",
                            source_hash,
                        ),
                    )
                    cur.execute("RELEASE SAVEPOINT sp_record")
                    records_inserted += 1

                    if records_inserted % batch_size == 0:
                        conn.commit()
                        logger.debug("Committed batch: %d records so far", records_inserted)

                except ValidationError as e:
                    cur.execute("ROLLBACK TO SAVEPOINT sp_record")
                    records_failed += 1
                    errors.append({
                        "index": idx,
                        "article_id": raw_record.get("article_id"),
                        "error": str(e),
                    })
                    if records_failed <= 5:
                        logger.warning(
                            "Validation error at index %d (article_id=%s): %s",
                            idx, raw_record.get("article_id"), e,
                        )

                except Exception as e:
                    cur.execute("ROLLBACK TO SAVEPOINT sp_record")
                    records_failed += 1
                    errors.append({
                        "index": idx,
                        "article_id": raw_record.get("article_id"),
                        "error": str(e),
                    })
                    logger.error(
                        "Error at index %d (article_id=%s): %s",
                        idx, raw_record.get("article_id"), e,
                    )

            # Final commit
            conn.commit()

    logger.info(
        "Journal RSS load complete: %d inserted, %d failed",
        records_inserted, records_failed,
    )

    return {
        "status": "success" if records_failed == 0 else "partial",
        "records_inserted": records_inserted,
        "records_failed": records_failed,
        "errors": errors[:10],
    }


def _parse_date(value: Any) -> Optional[date]:
    """Best-effort parsing of a date value.

    Accepts ISO strings (YYYY-MM-DD), datetime objects, date objects,
    or None.
    """
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                return datetime.strptime(value[: len(fmt.replace("%", "0"))], fmt).date()
            except (ValueError, IndexError):
                continue
        try:
            return datetime.fromisoformat(value).date()
        except (ValueError, TypeError):
            pass
    return None
