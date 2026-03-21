"""USPTO CI (Competitive Intelligence) Fetcher.

Feature: 011-datasource-integration
Task: T055-T057 — USPTO PatentsView CI source integration

Fetches pharmaceutical-relevant patents from the USPTO PatentSearch API.
Queries are scoped by search terms read from meta.ops_ci_search_terms
(drug_name, therapeutic_area) and filtered by CPC codes A61K, A61P,
C07D (pharmaceutical chemistry).

Weekly cadence with cursor-based pagination.

Source: https://search.patentsview.org/api/v1/patent/
"""

import hashlib
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# PatentSearch API endpoint — configurable for March 2026 migration to data.uspto.gov
PATENTSVIEW_API = os.environ.get(
    "PATENTSVIEW_API_URL",
    "https://search.patentsview.org/api/v1/patent/",
)

# CPC codes relevant to pharmaceutical chemistry
PHARMA_CPC_CODES = ["A61K", "A61P", "C07D"]

# Pagination settings
PAGE_SIZE = 100
MAX_PAGES = 50  # Safety limit

# PatentsView API rate limit: 45 req/min per API key
REQUEST_DELAY = 1.4  # seconds between requests


class USPTOCIFetcher(BaseFetcher):
    """Fetcher for USPTO PatentSearch API (CI scope)."""

    SOURCE_NAME = "uspto_ci"
    BASE_URL = os.environ.get("PATENTSVIEW_BASE_URL", "https://search.patentsview.org")

    def __init__(self, data_dir: Optional[str] = None):
        """Initialize the USPTO CI fetcher with optional API key."""
        super().__init__(data_dir)

        self.api_key: Optional[str] = os.environ.get("PATENTSVIEW_API_KEY")
        if self.api_key:
            self.session.headers.update({"X-Api-Key": self.api_key})
            logger.info("PatentsView API key configured")
        else:
            logger.info(
                "PATENTSVIEW_API_KEY not set; PatentsView requests may be rate-limited"
            )

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
                # Default fallback terms when meta.ops_ci_search_terms is empty
                search_terms = [
                    "dupilumab",
                    "semaglutide",
                    "pembrolizumab",
                    "adalimumab",
                    "nivolumab",
                ]
                logger.info(
                    "No search terms from DB; using %d default pharma terms for USPTO CI",
                    len(search_terms),
                )

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
                "record_count": len(all_records),
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
        """Read search terms from meta.ops_ci_search_terms.

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
                        FROM meta.ops_ci_search_terms
                        WHERE term_type IN ('drug_name', 'therapeutic_area')
                          AND is_active = TRUE
                        ORDER BY term_id
                        """
                    )
                    rows = cur.fetchall()

            terms = [row[0] for row in rows]
            if terms:
                logger.info(
                    "Loaded %d search terms from meta.ops_ci_search_terms",
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
        """Build a PatentSearch API query payload.

        Combines text search terms (OR) with CPC code filtering (OR)
        and a date range filter.

        Args:
            search_terms: List of keyword strings.
            since_date: ISO date string for grant_date lower bound.

        Returns:
            Query dict for the PatentSearch API.
        """
        # Text criteria: match any search term in title or abstract
        text_clauses = [
            {"_or": [
                {"_text_any": {"patent_title": term}},
                {"_text_any": {"patent_abstract": term}},
            ]}
            for term in search_terms
        ]

        # CPC code criteria (fully qualified nested field name)
        cpc_clauses = [
            {"_begins": {"cpc_current.cpc_subgroup_id": code}}
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
        """Fetch paginated results from the PatentSearch API.

        Uses cursor-based pagination with size/after parameters.

        Args:
            query: PatentSearch query dict.
            max_pages: Safety limit for pagination.

        Returns:
            List of normalized patent record dicts.
        """
        all_records: List[Dict[str, Any]] = []
        # Fields to return — PatentSearch API field names
        fields = [
            "patent_id",
            "patent_title",
            "patent_abstract",
            "patent_date",
            "patent_num_claims",
            "inventors",
            "assignees",
            "cpc_current",
            "application",
        ]

        after_cursor: Optional[str] = None

        for _page in range(1, max_pages + 1):
            options: Dict[str, Any] = {"size": PAGE_SIZE}
            if after_cursor:
                options["after"] = after_cursor

            payload = {
                "q": query,
                "f": fields,
                "o": options,
            }

            try:
                response = self.session.post(
                    PATENTSVIEW_API,
                    json=payload,
                    timeout=60,
                )
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                logger.warning(
                    "PatentSearch API request failed at cursor %s: %s",
                    after_cursor, e,
                )
                break

            patents = data.get("patents")
            if not patents:
                break

            for patent in patents:
                record = self._normalize_patent(patent)
                if record:
                    all_records.append(record)

            # Rate limit: 45 req/min for PatentsView API
            time.sleep(REQUEST_DELAY)

            # Stop when we receive fewer results than the page size
            if len(patents) < PAGE_SIZE:
                break

            # Cursor for next page: last patent_id in results
            last_patent = patents[-1]
            after_cursor = str(last_patent.get("patent_id", ""))
            if not after_cursor:
                break

        logger.info(
            "Fetched %d patent records from PatentSearch", len(all_records)
        )
        return all_records

    @staticmethod
    def _normalize_patent(patent: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize a PatentSearch patent record to the raw.uspto_ci schema.

        Args:
            patent: Raw patent dict from the API.

        Returns:
            Normalized record dict, or None if patent_id is missing.
        """
        patent_id = patent.get("patent_id")
        if not patent_id:
            return None

        # Normalize inventors (match Patents fetcher schema)
        inventors = None
        raw_inventors = patent.get("inventors")
        if raw_inventors and isinstance(raw_inventors, list):
            inventors = [
                {
                    "name_first": inv.get("inventor_name_first"),
                    "name_last": inv.get("inventor_name_last"),
                }
                for inv in raw_inventors
            ]

        # Normalize assignees (match Patents fetcher schema)
        assignees = None
        raw_assignees = patent.get("assignees")
        if raw_assignees and isinstance(raw_assignees, list):
            assignees = [
                {
                    "organization": asg.get("assignee_organization"),
                }
                for asg in raw_assignees
            ]

        # CPC codes (PatentSearch uses cpc_current instead of cpcs)
        cpc_codes = None
        raw_cpcs = patent.get("cpc_current")
        if isinstance(raw_cpcs, list):
            cpc_codes = [
                c.get("cpc_subgroup_id", "") if isinstance(c, dict) else str(c)
                for c in raw_cpcs
            ]

        # Filing date from nested application object
        application = patent.get("application") or {}
        filing_date = application.get("filing_date")

        # Claims count — explicit int cast for safety
        claims_count = patent.get("patent_num_claims")
        if claims_count is not None:
            try:
                claims_count = int(claims_count)
            except (ValueError, TypeError):
                claims_count = None

        return {
            "patent_id": str(patent_id),
            "title": patent.get("patent_title"),
            "abstract": patent.get("patent_abstract"),
            "inventors": inventors,
            "assignees": assignees,
            "filing_date": filing_date,
            "grant_date": patent.get("patent_date"),
            "cpc_codes": cpc_codes,
            "claims_count": claims_count,
        }
