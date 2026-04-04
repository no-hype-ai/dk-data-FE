"""EuropePMC REST API Fetcher.

Feature: 011-datasource-integration
Task: EuropePMC literature source integration

Fetches pharma-relevant publications from Europe PMC using the REST search API
with cursor-based pagination.  Records are stored as-is (raw JSONB) in
mol_raw.europepmc by the loader, so field names here must match the
EuropePMC search API response schema.

API Docs: https://europepmc.org/RestfulWebService#!/Europe32PMC32Articles32RESTful32API
Rate limit: 10 req/s (unauthenticated); use polite pool via email param.

Key API response fields (per search result):
    id, pmid, pmcid, doi, title, abstractText, authorString,
    authorList.author[].fullName, journalTitle, firstPublicationDate,
    pubYear, citedByCount, isOpenAccess, inEPMC, pubType,
    meshHeadingList.meshHeading[].descriptorName,
    keywordList.keyword[], source, resultList.result
"""

import hashlib
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# EuropePMC REST API base URL
BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"

# Max records per search page (API cap: 1000)
PAGE_SIZE = 100

# Hard cap per fetch run — None means unlimited
MAX_RECORDS = None

# Polite delay between pages (10 req/s limit)
REQUEST_DELAY = 0.12


class EuropePMCFetcher(BaseFetcher):
    """Fetcher for EuropePMC publications.

    Uses the /search endpoint with cursor-based pagination.
    Results are stored as raw JSONB in mol_raw.europepmc.
    """

    SOURCE_NAME = "europepmc"
    BASE_URL = BASE_URL

    # Default search: pharma-relevant MeSH terms
    DEFAULT_QUERY = (
        '(MESH:"Pharmaceutical Preparations" OR MESH:"Drug Therapy" '
        'OR MESH:"Clinical Trials as Topic" OR PUB_TYPE:"clinical-trial")'
    )

    def __init__(self, data_dir: Optional[str] = None) -> None:
        """Initialize the EuropePMC fetcher."""
        super().__init__(data_dir)
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "DK-Data-Platform/1.0 (mailto:data-platform@datakinetic.com)",
        })

    def get_latest_url(self) -> str:
        """Return the EuropePMC search endpoint URL."""
        return f"{BASE_URL}/search"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch recent publications from EuropePMC.

        Keyword Args:
            query: EuropePMC search query. Defaults to pharma mesh terms.
            days_back: Number of days to look back. Defaults to 7.
            max_records: Maximum records to fetch. Defaults to 5000.
            open_access_only: Filter to open-access only. Defaults to False.

        Returns:
            Dict with keys: status, records, record_count, hash, error (on failure).
        """
        query: str = kwargs.get("query", self.DEFAULT_QUERY)
        raw_days_back = kwargs.get("days_back", None)
        days_back: Optional[int] = int(raw_days_back) if raw_days_back is not None else None
        raw_max = kwargs.get("max_records", MAX_RECORDS)
        max_records: Optional[int] = int(raw_max) if raw_max is not None else None
        open_access_only: bool = bool(kwargs.get("open_access_only", False))

        try:
            # Build date filter only when days_back is explicitly set
            full_query = query
            if days_back is not None:
                from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
                full_query = f"{query} AND FIRST_PDATE:[{from_date} TO *]"
            if open_access_only:
                full_query += " AND OPEN_ACCESS:y"

            logger.info(
                "Fetching EuropePMC publications (days_back=%d, max=%d)",
                days_back, max_records,
            )

            records = self._paginate(full_query, max_records=max_records)

            content_hash = hashlib.md5(
                str(sorted(r.get("pmid", r.get("id", "")) for r in records)).encode()
            ).hexdigest()

            result = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except Exception as exc:
            logger.exception("EuropePMC fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _paginate(self, query: str, max_records: Optional[int]) -> List[Dict[str, Any]]:
        """Paginate through EuropePMC search results using cursorMark."""
        all_records: List[Dict[str, Any]] = []
        cursor_mark = "*"
        url = self.get_latest_url()

        while max_records is None or len(all_records) < max_records:
            page_size = min(PAGE_SIZE, (max_records - len(all_records)) if max_records is not None else PAGE_SIZE)

            params = {
                "query": query,
                "format": "json",
                "pageSize": page_size,
                "cursorMark": cursor_mark,
                "resultType": "core",  # full record including abstractText
            }

            try:
                data = self.fetch_json(url, params=params)
            except Exception as exc:
                logger.warning("EuropePMC page fetch failed at cursor=%s: %s", cursor_mark, exc)
                if cursor_mark == "*":
                    # First page failure — propagate so fetch() returns 'failed'
                    raise
                break

            result_list = data.get("resultList", {})
            results = result_list.get("result", [])

            if not results:
                break

            all_records.extend(results)

            next_cursor = data.get("nextCursorMark")
            if not next_cursor or next_cursor == cursor_mark:
                break

            cursor_mark = next_cursor
            time.sleep(REQUEST_DELAY)

        logger.info("EuropePMC paginated: %d records retrieved", len(all_records))
        return all_records
