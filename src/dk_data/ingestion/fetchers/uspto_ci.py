"""USPTO CI (Competitive Intelligence) Fetcher.

Feature: 011-datasource-integration
Task: T055-T057 — USPTO PatentsView CI source integration

Fetches pharmaceutical-relevant patents from the USPTO PatentsView API
v1.  Queries are scoped by search terms read from meta.ci_search_terms
(drug_name, therapeutic_area) and filtered by CPC codes A61K, A61P,
C07D (pharmaceutical chemistry).

Weekly cadence with pagination via page/per_page parameters.

Source: https://api.patentsview.org
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# PatentsView API endpoint
PATENTSVIEW_API = "https://api.patentsview.org/patents/query"

# CPC codes relevant to pharmaceutical chemistry
PHARMA_CPC_CODES = ["A61K", "A61P", "C07D"]

# Pagination settings
PAGE_SIZE = 100
MAX_PAGES = 50  # Safety limit


class USPTOCIFetcher(BaseFetcher):
    """Fetcher for USPTO PatentsView API (CI scope)."""

    SOURCE_NAME = "uspto_ci"
    BASE_URL = "https://api.patentsview.org"

    def get_latest_url(self) -> str:
        """Return the PatentsView query endpoint URL."""
        return PATENTSVIEW_API

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch pharmaceutical patents from the USPTO PatentsView API.

        Keyword Args:
            days_back: Number of days to look back for grants (default: 7).
            max_pages: Maximum number of pages to fetch (default: 50).
            search_terms: Optional list of search term strings.
                          If not provided, reads from DB.

        Returns:
            Dict with keys: status, records, hash, error (on failure).
        """
        days_back = kwargs.get("days_back", 7)
        max_pages = kwargs.get("max_pages", MAX_PAGES)

        try:
            search_terms = kwargs.get("search_terms") or self._get_search_terms()

            if not search_terms:
                logger.warning("No USPTO CI search terms configured")
                result: Dict[str, Any] = {
                    "status": "success",
                    "records": [],
                    "hash": None,
                    "message": "No search terms configured",
                }
                self.log_fetch_result(result)
                return result

            logger.info(
                "Fetching USPTO patents (days_back=%d, terms=%d)",
                days_back, len(search_terms),
            )

            since_date = (
                datetime.utcnow() - timedelta(days=days_back)
            ).strftime("%Y-%m-%d")

            all_records: List[Dict[str, Any]] = []
            seen_ids: set = set()

            # Build and execute the query
            query = self._build_query(search_terms, since_date)
            records = self._fetch_paginated(query, max_pages=max_pages)

            for record in records:
                patent_id = record.get("patent_id")
                if patent_id and patent_id not in seen_ids:
                    seen_ids.add(patent_id)
                    all_records.append(record)

            # Compute content hash
            content_hash = hashlib.md5(
                ",".join(sorted(seen_ids)).encode()
            ).hexdigest() if seen_ids else None

            result = {
                "status": "success",
                "records": all_records,
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(all_records)})
            return result

        except Exception as e:
            logger.exception("USPTO CI fetch failed: %s", e)
            result = {
                "status": "failed",
                "records": [],
                "hash": None,
                "error": str(e),
            }
            self.log_fetch_result(result)
            return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_search_terms(self) -> List[str]:
        """Read search terms from meta.ci_search_terms.

        Returns:
            List of search term strings.
        """
        try:
            from ..utils.database import get_connection

            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT term_value
                        FROM meta.ci_search_terms
                        WHERE term_type IN ('drug_name', 'therapeutic_area')
                          AND is_active = TRUE
                        ORDER BY term_id
                        """
                    )
                    rows = cur.fetchall()

            terms = [row[0] for row in rows]
            if terms:
                logger.info(
                    "Loaded %d search terms from meta.ci_search_terms",
                    len(terms),
                )
            return terms

        except Exception as e:
            logger.warning(
                "Could not read search terms from DB: %s", e
            )
            return []

    @staticmethod
    def _build_query(
        search_terms: List[str], since_date: str
    ) -> Dict[str, Any]:
        """Build a PatentsView API query payload.

        Combines text search terms (OR) with CPC code filtering (OR)
        and a date range filter.

        Args:
            search_terms: List of keyword strings.
            since_date: ISO date string for grant_date lower bound.

        Returns:
            Query dict for the PatentsView API.
        """
        # Text criteria: match any search term in title or abstract
        text_clauses = [
            {"_or": [
                {"_text_any": {"patent_title": term}},
                {"_text_any": {"patent_abstract": term}},
            ]}
            for term in search_terms
        ]

        # CPC code criteria
        cpc_clauses = [
            {"_begins": {"cpc_subgroup_id": code}}
            for code in PHARMA_CPC_CODES
        ]

        query = {
            "_and": [
                {"_gte": {"patent_date": since_date}},
                {"_or": cpc_clauses},
                {"_or": text_clauses},
            ]
        }
        return query

    def _fetch_paginated(
        self, query: Dict[str, Any], *, max_pages: int = MAX_PAGES
    ) -> List[Dict[str, Any]]:
        """Fetch paginated results from the PatentsView API.

        Args:
            query: PatentsView query dict.
            max_pages: Safety limit for pagination.

        Returns:
            List of normalized patent record dicts.
        """
        all_records: List[Dict[str, Any]] = []
        fields = [
            "patent_number",
            "patent_title",
            "patent_abstract",
            "patent_date",
            "patent_num_claims",
        ]

        for page in range(1, max_pages + 1):
            payload = {
                "q": json.dumps(query),
                "f": json.dumps(fields),
                "o": json.dumps({
                    "page": page,
                    "per_page": PAGE_SIZE,
                }),
            }

            try:
                data = self.fetch_json(PATENTSVIEW_API, params=payload)
            except Exception as e:
                logger.warning(
                    "PatentsView API request failed on page %d: %s",
                    page, e,
                )
                break

            patents = data.get("patents")
            if not patents:
                break

            for patent in patents:
                record = self._normalize_patent(patent)
                if record:
                    all_records.append(record)

            # Stop when we receive fewer results than the page size
            if len(patents) < PAGE_SIZE:
                break

        logger.info(
            "Fetched %d patent records from PatentsView", len(all_records)
        )
        return all_records

    @staticmethod
    def _normalize_patent(patent: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize a PatentsView patent record to the raw.uspto_ci schema.

        Args:
            patent: Raw patent dict from the API.

        Returns:
            Normalized record dict, or None if patent_number is missing.
        """
        patent_number = patent.get("patent_number")
        if not patent_number:
            return None

        # Inventors (nested in API response)
        inventors = patent.get("inventors")

        # Assignees (nested in API response)
        assignees = patent.get("assignees")

        # CPC codes (nested list)
        cpc_codes = None
        raw_cpcs = patent.get("cpcs") or patent.get("cpc_subgroup_id")
        if isinstance(raw_cpcs, list):
            cpc_codes = [
                c.get("cpc_subgroup_id", "") if isinstance(c, dict) else str(c)
                for c in raw_cpcs
            ]

        return {
            "patent_id": str(patent_number),
            "title": patent.get("patent_title"),
            "abstract": patent.get("patent_abstract"),
            "inventors": inventors,
            "assignees": assignees,
            "filing_date": patent.get("app_date"),
            "grant_date": patent.get("patent_date"),
            "cpc_codes": cpc_codes,
            "claims_count": patent.get("patent_num_claims"),
        }
