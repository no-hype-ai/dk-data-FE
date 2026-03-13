"""USPTO Patents Data Fetcher.

Feature: 011-datasource-integration
Task: Phase 6 / US4 — credential-gated source (USPTO PatentsView)

Fetches pharmaceutical patent data from the PatentSearch API using
API key authentication. Filters by CPC codes A61K, A61P, C07D
for pharma-relevant patents. Weekly refresh cadence.

Source: https://search.patentsview.org/api/v1/patent/
Docs: https://search.patentsview.org/docs/docs/Search%20API/SearchAPIReference/
"""

import hashlib
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# CPC codes for pharmaceutical patents
PHARMA_CPC_CODES = ["A61K", "A61P", "C07D"]

# PatentSearch API page size (max 1000)
PAGE_SIZE = 100

# Safety limit: max records per fetch run
MAX_RECORDS = 10_000

# PatentsView API rate limit: 45 req/min per API key
REQUEST_DELAY = 1.4  # seconds between requests


class USPTOPatentsFetcher(BaseFetcher):
    """Fetcher for USPTO PatentSearch pharmaceutical patents."""

    SOURCE_NAME = "uspto_patents"
    BASE_URL = os.environ.get("PATENTSVIEW_BASE_URL", "https://search.patentsview.org")

    # PatentSearch API endpoint — configurable for March 2026 migration to data.uspto.gov
    PATENTS_API = os.environ.get(
        "PATENTSVIEW_API_URL",
        "https://search.patentsview.org/api/v1/patent/",
    )

    def __init__(self, data_dir: Optional[str] = None):
        """Initialize the USPTO Patents fetcher.

        Reads USPTO_API_KEY from the environment.

        Args:
            data_dir: Directory to store downloaded files.
        """
        super().__init__(data_dir)
        self.api_key: Optional[str] = (
            os.environ.get("PATENTSVIEW_API_KEY")
            or os.environ.get("USPTO_API_KEY")
        )
        if self.api_key:
            logger.info("PatentsView API key detected")
        else:
            logger.warning(
                "No PATENTSVIEW_API_KEY (or USPTO_API_KEY) set. "
                "The PatentsView API requires an API key — requests will return 403. "
                "Get a key at https://patentsview.org/apis/keyrequest"
            )

    def get_latest_url(self) -> str:
        """Get the PatentSearch API query endpoint URL."""
        return self.PATENTS_API

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch pharmaceutical patents from the PatentSearch API.

        Keyword Args:
            days_back: Number of days to look back for grants (default: 7).
            cpc_codes: List of CPC codes to filter by (default: pharma codes).
            max_records: Maximum records to fetch (default: 10000).

        Returns:
            Dictionary with:
                - status: 'success' or 'failed'
                - records: list of patent record dicts
                - record_count: number of records fetched
                - hash: SHA-256 hash of the content
                - error: error message (if failed)
        """
        days_back = kwargs.get("days_back", 7)
        cpc_codes = kwargs.get("cpc_codes", PHARMA_CPC_CODES)
        max_records = kwargs.get("max_records", MAX_RECORDS)

        try:
            logger.info(
                "Fetching USPTO patents (days_back=%d, CPC codes=%s)",
                days_back,
                cpc_codes,
            )

            all_records: List[Dict[str, Any]] = []
            after_cursor: Optional[str] = None

            while len(all_records) < max_records:
                data = self._fetch_page(
                    days_back=days_back,
                    cpc_codes=cpc_codes,
                    after=after_cursor,
                )

                patents = data.get("patents") or []
                if not patents:
                    logger.info("No more patents from PatentSearch API")
                    break

                for patent in patents:
                    record = self._normalize_patent(patent)
                    if record:
                        all_records.append(record)

                # Stop if we got fewer than a full page
                if len(patents) < PAGE_SIZE:
                    break

                # Rate limit: 45 req/min for PatentsView API
                time.sleep(REQUEST_DELAY)

                # Cursor-based pagination: use last patent_id as cursor
                last_patent = patents[-1]
                after_cursor = str(last_patent.get("patent_id", ""))
                if not after_cursor:
                    break

                if len(all_records) >= max_records:
                    all_records = all_records[:max_records]
                    break

            # Compute content hash
            content_hash = hashlib.sha256(
                str(sorted(r["patent_number"] for r in all_records)).encode()
            ).hexdigest()

            result = {
                "status": "success",
                "records": all_records,
                "record_count": len(all_records),
                "hash": content_hash,
            }

            logger.info("USPTO Patents fetch complete: %d records", len(all_records))
            self.log_fetch_result({"status": "success", "records": len(all_records)})
            return result

        except Exception as e:
            logger.exception("Failed to fetch USPTO Patents data: %s", e)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(e),
            }
            self.log_fetch_result(result)
            return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_page(
        self,
        days_back: int = 7,
        cpc_codes: Optional[List[str]] = None,
        after: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch a single page of patents from the PatentSearch API.

        Args:
            days_back: Look-back window in days.
            cpc_codes: CPC code prefixes to filter.
            after: Cursor for pagination (last patent_id from previous page).

        Returns:
            Raw API response dict.
        """
        if cpc_codes is None:
            cpc_codes = PHARMA_CPC_CODES

        since_date = (
            datetime.utcnow() - timedelta(days=days_back)
        ).strftime("%Y-%m-%d")

        # Build the query filter for CPC codes (fully qualified nested field)
        cpc_conditions = [
            {"_begins": {"cpc_current.cpc_subgroup_id": code}}
            for code in cpc_codes
        ]

        query = {
            "_and": [
                {"_gte": {"patent_date": since_date}},
                {"_or": cpc_conditions},
            ]
        }

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

        # Cursor-based pagination
        options: Dict[str, Any] = {"size": PAGE_SIZE}
        if after:
            options["after"] = after

        payload = {
            "q": query,
            "f": fields,
            "o": options,
        }

        headers = {
            "Content-Type": "application/json",
        }

        if self.api_key:
            headers["X-Api-Key"] = self.api_key

        logger.debug("PatentSearch API request after=%s", after)
        response = self.session.post(
            self.get_latest_url(),
            json=payload,
            headers=headers,
            timeout=120,
        )
        response.raise_for_status()

        return response.json()

    def _normalize_patent(self, patent: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize a PatentSearch patent record.

        Args:
            patent: Raw patent dict from the PatentSearch API.

        Returns:
            Normalized record dict, or None if patent_id is missing.
        """
        patent_id = patent.get("patent_id")
        if not patent_id:
            return None

        patent_number = str(patent_id).strip()

        # Parse inventors (PatentSearch uses inventor_name_first/inventor_name_last)
        inventors = None
        raw_inventors = patent.get("inventors")
        if raw_inventors and isinstance(raw_inventors, list):
            inventors = [
                {
                    "name_first": inv.get("inventor_name_first"),
                    "name_last": inv.get("inventor_name_last"),
                    "city": inv.get("inventor_city"),
                    "state": inv.get("inventor_state"),
                    "country": inv.get("inventor_country"),
                }
                for inv in raw_inventors
            ]

        # Parse assignees
        assignees = None
        raw_assignees = patent.get("assignees")
        if raw_assignees and isinstance(raw_assignees, list):
            assignees = [
                {
                    "organization": asg.get("assignee_organization"),
                    "city": asg.get("assignee_city"),
                    "state": asg.get("assignee_state"),
                    "country": asg.get("assignee_country"),
                }
                for asg in raw_assignees
            ]

        # Parse CPC codes (PatentSearch uses cpc_current instead of cpcs)
        cpc_codes = None
        raw_cpcs = patent.get("cpc_current")
        if raw_cpcs and isinstance(raw_cpcs, list):
            cpc_codes = list({
                cpc.get("cpc_subgroup_id")
                for cpc in raw_cpcs
                if cpc.get("cpc_subgroup_id")
            })

        # Parse filing date from nested application object
        application = patent.get("application") or {}
        filing_date = application.get("filing_date")

        # Grant date
        grant_date = patent.get("patent_date")

        # Claims count
        claims_count = patent.get("patent_num_claims")
        if claims_count is not None:
            try:
                claims_count = int(claims_count)
            except (ValueError, TypeError):
                claims_count = None

        return {
            "patent_number": patent_number,
            "title": patent.get("patent_title"),
            "abstract": patent.get("patent_abstract"),
            "inventors": inventors,
            "assignees": assignees,
            "filing_date": filing_date,
            "grant_date": grant_date,
            "cpc_codes": cpc_codes,
            "claims_count": claims_count,
        }
