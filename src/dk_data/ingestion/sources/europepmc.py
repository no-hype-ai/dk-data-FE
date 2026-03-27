"""EuropePMC loader — inserts to mol_raw.europepmc_raw."""
import logging
from datetime import datetime
from typing import List, Optional

from ..utils.database import get_cursor, upsert_records

logger = logging.getLogger(__name__)


def load_europepmc_data(records: list, source_hash: Optional[str] = None) -> dict:
    """
    Load EuropePMC records into mol_raw.europepmc_raw.

    Args:
        records: List of raw API response dicts from EuropePMCFetcher.
        source_hash: Optional content hash string (unused for this source).

    Returns:
        Standard result dict with status, records_fetched, records_inserted, records_updated, errors.
    """
    if not records:
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    rows = []
    errors: List[str] = []

    for r in records:
        pmid = r.get("pmid")
        if not pmid:
            continue
        try:
            journal_title = None
            journal_info = r.get("journalInfo")
            if isinstance(journal_info, dict):
                journal_obj = journal_info.get("journal")
                if isinstance(journal_obj, dict):
                    journal_title = journal_obj.get("title")

            author_list_raw = r.get("authorList", {})
            if isinstance(author_list_raw, dict):
                authors = author_list_raw.get("author", [])
            else:
                authors = []

            rows.append({
                "pmid": str(pmid),
                "doi": r.get("doi"),
                "title": r.get("title"),
                "abstract_text": r.get("abstractText"),
                "journal_title": journal_title,
                "publication_date": r.get("firstPublicationDate"),
                "publication_year": str(r.get("pubYear")) if r.get("pubYear") else None,
                "author_list": str(authors),
                "response_body": str(r),
                "_loaded_at": datetime.utcnow(),
            })
        except Exception as e:
            errors.append(f"pmid={pmid}: {e}")
            logger.warning(f"EuropePMC row error for pmid={pmid}: {e}")

    if not rows:
        return {
            "status": "success",
            "records_fetched": len(records),
            "records_inserted": 0,
            "records_updated": 0,
            "errors": errors[:10],
        }

    inserted = upsert_records(
        "mol_raw",
        "europepmc_raw",
        rows,
        conflict_columns=["pmid"],
        update_columns=["title", "abstract_text", "publication_date", "_loaded_at"],
    )

    logger.info(
        f"EuropePMC load complete: {inserted} upserted from {len(records)} fetched records"
    )

    return {
        "status": "success",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
