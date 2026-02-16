"""USPTO Patents Data Fetcher.

Feature: 011-datasource-integration
Task: Phase 6 / US4 — credential-gated source (USPTO PatentsView)

Fetches pharmaceutical patent data from the PatentsView API v1 using
API key authentication. Filters by CPC codes A61K, A61P, C07D
for pharma-relevant patents. Weekly refresh cadence.

Source: https://api.patentsview.org
Docs: https://patentsview.org/apis/api-endpoints
"""

import hashlib
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# CPC codes for pharmaceutical patents
PHARMA_CPC_CODES = ["A61K", "A61P", "C07D"]

# PatentsView API page size (max 1000)
PAGE_SIZE = 100

# Safety limit: max records per fetch run
MAX_RECORDS = 10_000


class USPTOPatentsFetcher(BaseFetcher):
    """Fetcher for USPTO PatentsView pharmaceutical patents."""

    SOURCE_NAME = "uspto_patents"
    BASE_URL = "https://api.patentsview.org"

    # PatentsView query endpoint
    PATENTS_API = "https://api.patentsview.org/patents/query"

    def __init__(self, data_dir: Optional[str] = None):
        """Initialize the USPTO Patents fetcher.

        Reads USPTO_API_KEY from the environment.

        Args:
            data_dir: Directory to store downloaded files.
        """
        super().__init__(data_dir)
        self.api_key: Optional[str] = os.environ.get("USPTO_API_KEY")
        if self.api_key:
            logger.info("USPTO API key detected")
        else:
            logger.warning(
                "No USPTO_API_KEY set; USPTO Patents fetch may fail or be rate-limited"
            )

    def get_latest_url(self) -> str:
        """Get the PatentsView API query endpoint URL."""
        return self.PATENTS_API

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch pharmaceutical patents from the PatentsView API.

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
            page = 1

            while len(all_records) < max_records:
                data = self._fetch_page(
                    days_back=days_back,
                    cpc_codes=cpc_codes,
                    page=page,
                )

                patents = data.get("patents") or []
                if not patents:
                    logger.info("No more patents from PatentsView API")
                    break

                for patent in patents:
                    record = self._normalize_patent(patent)
                    if record:
                        all_records.append(record)

                # Stop if we got fewer than a full page
                if len(patents) < PAGE_SIZE:
                    break

                page += 1

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
        page: int = 1,
    ) -> Dict[str, Any]:
        """Fetch a single page of patents from the PatentsView API.

        Args:
            days_back: Look-back window in days.
            cpc_codes: CPC code prefixes to filter.
            page: Page number (1-based).

        Returns:
            Raw API response dict.
        """
        if cpc_codes is None:
            cpc_codes = PHARMA_CPC_CODES

        since_date = (
            datetime.utcnow() - timedelta(days=days_back)
        ).strftime("%Y-%m-%d")

        # Build the query filter for CPC codes
        cpc_conditions = [
            {"_begins": {"cpc_subgroup_id": code}}
            for code in cpc_codes
        ]

        query = {
            "_and": [
                {"_gte": {"patent_date": since_date}},
                {"_or": cpc_conditions},
            ]
        }

        # Fields to return — must include all fields used by _normalize_patent
        fields = [
            "patent_number",
            "patent_title",
            "patent_abstract",
            "patent_date",
            "patent_num_claims",
            "inventors",
            "assignees",
            "cpcs",
            "app_date",
        ]

        payload = {
            "q": query,
            "f": fields,
            "o": {
                "page": page,
                "per_page": PAGE_SIZE,
            },
        }

        headers = {
            "Content-Type": "application/json",
        }

        if self.api_key:
            headers["X-Api-Key"] = self.api_key

        logger.debug("PatentsView API request page=%d", page)
        response = self.session.post(
            self.get_latest_url(),
            json=payload,
            headers=headers,
            timeout=120,
        )
        response.raise_for_status()

        return response.json()

    def _normalize_patent(self, patent: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize a PatentsView patent record.

        Args:
            patent: Raw patent dict from the PatentsView API.

        Returns:
            Normalized record dict, or None if patent_number is missing.
        """
        patent_number = patent.get("patent_number")
        if not patent_number:
            return None

        patent_number = str(patent_number).strip()

        # Parse inventors
        inventors = None
        raw_inventors = patent.get("inventors")
        if raw_inventors and isinstance(raw_inventors, list):
            inventors = [
                {
                    "name_first": inv.get("inventor_first_name"),
                    "name_last": inv.get("inventor_last_name"),
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

        # Parse CPC codes
        cpc_codes = None
        raw_cpcs = patent.get("cpcs")
        if raw_cpcs and isinstance(raw_cpcs, list):
            cpc_codes = list({
                cpc.get("cpc_subgroup_id")
                for cpc in raw_cpcs
                if cpc.get("cpc_subgroup_id")
            })

        # Parse dates
        filing_date = patent.get("app_date") or patent.get("application_date")
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
