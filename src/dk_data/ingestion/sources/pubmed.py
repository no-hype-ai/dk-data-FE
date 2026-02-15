"""PubMed literature data loader.

Feature: 011-datasource-integration
Task: PubMed CI source integration

Loads PubMed article records (from the PubMedFetcher output) into
the raw.pubmed table with upsert semantics on the PMID.
"""

import json
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..utils.database import get_connection
from ..utils.validators import PubMedRecord

logger = logging.getLogger(__name__)


def load_pubmed_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load PubMed article records into raw.pubmed.

    Args:
        records: List of article dicts as returned by PubMedFetcher.fetch().
        source_hash: Optional content hash for tracking.
        source_file: Optional source file identifier.
        batch_size: Number of records to commit at once.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.info("No PubMed records to load")
        return {
            "status": "success",
            "records_inserted": 0,
            "records_failed": 0,
        }

    logger.info(f"Loading {len(records)} PubMed records into raw.pubmed")

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(records):
                try:
                    # Validate via Pydantic model
                    validated = PubMedRecord(
                        pmid=raw_record.get("pmid", ""),
                        title=raw_record.get("title"),
                        abstract=raw_record.get("abstract"),
                        authors=raw_record.get("authors"),
                        journal=raw_record.get("journal"),
                        publication_date=_parse_date(raw_record.get("publication_date")),
                        mesh_terms=raw_record.get("mesh_terms"),
                        doi=raw_record.get("doi"),
                        publication_types=raw_record.get("publication_types"),
                        keywords=raw_record.get("keywords"),
                    )

                    cur.execute(
                        """
                        INSERT INTO raw.pubmed (
                            pmid, title, abstract, authors, journal,
                            publication_date, mesh_terms, doi,
                            publication_types, keywords,
                            _source_file, _source_hash
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s,
                            %s, %s
                        )
                        ON CONFLICT (pmid) DO UPDATE SET
                            title = EXCLUDED.title,
                            abstract = EXCLUDED.abstract,
                            authors = EXCLUDED.authors,
                            journal = EXCLUDED.journal,
                            publication_date = EXCLUDED.publication_date,
                            mesh_terms = EXCLUDED.mesh_terms,
                            doi = EXCLUDED.doi,
                            publication_types = EXCLUDED.publication_types,
                            keywords = EXCLUDED.keywords,
                            _loaded_at = NOW(),
                            _source_file = EXCLUDED._source_file,
                            _source_hash = EXCLUDED._source_hash
                        """,
                        (
                            validated.pmid,
                            validated.title,
                            validated.abstract,
                            json.dumps(validated.authors) if validated.authors else None,
                            validated.journal,
                            validated.publication_date,
                            validated.mesh_terms if validated.mesh_terms else None,
                            validated.doi,
                            validated.publication_types if validated.publication_types else None,
                            validated.keywords if validated.keywords else None,
                            source_file,
                            source_hash,
                        ),
                    )
                    records_inserted += 1

                    # Commit in batches
                    if records_inserted % batch_size == 0:
                        conn.commit()
                        logger.debug(f"Committed {records_inserted} records")

                except ValidationError as e:
                    records_failed += 1
                    error_info = {
                        "index": idx,
                        "pmid": raw_record.get("pmid"),
                        "error": str(e),
                    }
                    errors.append(error_info)
                    if records_failed <= 10:
                        logger.warning(
                            f"Validation error at index {idx} "
                            f"(PMID={raw_record.get('pmid')}): {e}"
                        )

                except Exception as e:
                    records_failed += 1
                    error_info = {
                        "index": idx,
                        "pmid": raw_record.get("pmid"),
                        "error": str(e),
                    }
                    errors.append(error_info)
                    logger.error(
                        f"Error at index {idx} "
                        f"(PMID={raw_record.get('pmid')}): {e}"
                    )

            # Final commit
            conn.commit()

    logger.info(
        f"PubMed load complete: {records_inserted} inserted, "
        f"{records_failed} failed"
    )

    return {
        "status": "success" if records_failed == 0 else "partial",
        "records_inserted": records_inserted,
        "records_failed": records_failed,
        "source_hash": source_hash,
        "errors": errors[:10] if errors else [],
    }


def _parse_date(value: Any) -> Optional[date]:
    """Best-effort parsing of a date value from PubMed.

    Accepts ISO strings (YYYY-MM-DD), datetime objects, date objects,
    or None.
    """
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        # Try common formats
        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                return datetime.strptime(value[:len(fmt.replace("%", "0"))], fmt).date()
            except (ValueError, IndexError):
                continue
        # Fallback: try ISO parse
        try:
            return datetime.fromisoformat(value).date()
        except (ValueError, TypeError):
            pass
    return None
