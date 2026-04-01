"""Cochrane Library Systematic Reviews Fetcher.

Feature: 011-datasource-integration
Task: T064-T066 — Cochrane systematic reviews

Fetches systematic reviews from the Cochrane Library related to
pharmaceutical interventions, scoped by drug_name terms from
meta.ci_search_terms.

Source: https://www.cochranelibrary.com/cdsr/reviews
"""

import hashlib
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Max records per fetch run
MAX_RECORDS = 2000

# Rate limit: be respectful to Cochrane servers
REQUEST_DELAY = 2.0


class CochraneFetcher(BaseFetcher):
    """Fetcher for Cochrane Library systematic reviews."""

    SOURCE_NAME = "cochrane"
    BASE_URL = "https://www.cochranelibrary.com"

    # Cochrane search API endpoint
    SEARCH_API = "https://www.cochranelibrary.com/api/search"

    # Page size for search results
    PAGE_SIZE = 50

    def __init__(self, data_dir: Optional[str] = None):
        """Initialize the Cochrane fetcher."""
        super().__init__(data_dir)

        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "DK-Data-Platform/1.0 (Cochrane Research Integration)",
        })

    def get_latest_url(self) -> str:
        """Get the Cochrane search API URL."""
        return self.SEARCH_API

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch systematic reviews from Cochrane Library.

        Keyword Args:
            search_terms: List of drug names to search (default: from DB).
            max_records: Maximum records to fetch (default: 2000).
            days_back: Number of days to look back (default: 90).

        Returns:
            Dict with status, records, hash, error.
        """
        # Cochrane Library API (/api/search?searchBy=search-manager) was
        # permanently removed — requests return 404. A Wiley institutional
        # API license is now required for programmatic access.
        # No HTTP requests are made; return immediately.
        logger.info(
            "Cochrane Library API (/api/search) has been removed. "
            "Requires Wiley institutional API license. Returning source_unavailable."
        )
        result: Dict[str, Any] = {
            "status": "source_unavailable",
            "records": [],
            "record_count": 0,
            "hash": None,
            "error": (
                "Cochrane Library API (/api/search) has been removed. "
                "Requires Wiley institutional API license."
            ),
        }
        self.log_fetch_result(result)
        return result

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _search_reviews(
        self,
        term: str,
        *,
        days_back: int = 90,
        max_records: int = 2000,
    ) -> List[Dict[str, Any]]:
        """Search Cochrane for systematic reviews matching a term."""
        records: List[Dict[str, Any]] = []
        offset = 0
        date_from = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

        while len(records) < max_records:
            try:
                params = {
                    "searchBy": "search-manager",
                    "searchText": term,
                    "searchType": "standard",
                    "reviewType": "cdsr",
                    "resultPerPage": self.PAGE_SIZE,
                    "searchFrom": offset,
                    "publishDateFrom": date_from,
                }

                response = self.session.get(
                    self.get_latest_url(), params=params, timeout=30
                )
                if response.status_code in (401, 403):
                    # cochranelibrary.com/api/search requires institutional Wiley
                    # subscription. This endpoint is not publicly accessible.
                    # Contact Wiley for API access: https://documentation.cochrane.org/display/API
                    logger.warning(
                        "Cochrane API returned %d — endpoint requires institutional "
                        "Wiley subscription. Skipping.",
                        response.status_code,
                    )
                    break
                response.raise_for_status()
                data = response.json()

                items = self._extract_items(data)
                if not items:
                    break

                for item in items:
                    normalized = self._normalize_review(item, term)
                    if normalized:
                        records.append(normalized)

                if len(items) < self.PAGE_SIZE:
                    break

                offset += self.PAGE_SIZE
                time.sleep(REQUEST_DELAY)

            except Exception as e:
                logger.warning(
                    "Cochrane search failed for '%s' at offset %d: %s",
                    term, offset, e,
                )
                break

        return records

    @staticmethod
    def _extract_items(data: Any) -> List[Dict]:
        """Extract result items from Cochrane API response."""
        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            for key in ("results", "data", "items", "resultList"):
                if key in data and isinstance(data[key], list):
                    return data[key]

        return []

    def _normalize_review(
        self, item: Dict[str, Any], search_term: str
    ) -> Optional[Dict[str, Any]]:
        """Normalize a Cochrane review result into the raw schema."""
        review_id = (
            item.get("id")
            or item.get("reviewId")
            or item.get("doi")
            or item.get("cdNumber")
        )
        if not review_id:
            return None

        review_id = str(review_id).strip()

        # Parse authors
        authors = item.get("authors") or item.get("byline")
        if isinstance(authors, list):
            authors = "; ".join(str(a) for a in authors)
        elif authors:
            authors = str(authors)

        # Publication date
        pub_date = (
            item.get("publishDate")
            or item.get("publication_date")
            or item.get("date")
        )
        if pub_date:
            pub_date = str(pub_date)[:10]

        # Interventions
        interventions = item.get("interventions") or []
        if isinstance(interventions, str):
            interventions = [i.strip() for i in interventions.split(",")]

        # Conditions
        conditions = item.get("conditions") or item.get("healthConditions") or []
        if isinstance(conditions, str):
            conditions = [c.strip() for c in conditions.split(",")]

        return {
            "review_id": review_id,
            "title": item.get("title") or item.get("name"),
            "authors": authors,
            "abstract": item.get("abstract") or item.get("summary"),
            "publication_date": pub_date,
            "review_type": item.get("reviewType") or "systematic_review",
            "interventions": interventions if interventions else None,
            "conditions": conditions if conditions else None,
            "conclusions": item.get("conclusions") or item.get("authorsConclusions"),
            "doi": item.get("doi"),
        }

    # ------------------------------------------------------------------
    # Search terms from database
    # ------------------------------------------------------------------

    def _load_search_terms(self) -> List[str]:
        """Load active drug_name search terms from meta.ci_search_terms."""
        try:
            from ..utils.database import get_connection

            terms: List[str] = []
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT term_value
                        FROM meta.ci_search_terms
                        WHERE term_type = 'drug_name'
                          AND is_active = TRUE
                        ORDER BY term_value
                        """
                    )
                    for row in cur.fetchall():
                        terms.append(row[0])

            logger.info("Loaded %d drug_name terms from meta.ci_search_terms", len(terms))
            return terms

        except Exception as e:
            logger.warning("Could not load search terms from DB: %s", e)
            return []
