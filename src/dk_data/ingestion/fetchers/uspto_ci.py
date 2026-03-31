"""USPTO CI (Competitive Intelligence) Fetcher.

Feature: 011-datasource-integration
Task: T055-T057 — USPTO PatentsView CI source integration

Fetches pharmaceutical-relevant patents from the USPTO Open Data Portal (ODP).
Queries are scoped by search terms read from meta.ci_search_terms
(drug_name, therapeutic_area) and filtered by CPC codes A61K, A61P,
C07D (pharmaceutical chemistry).

Migration (March 20, 2026 — issue #131): search.patentsview.org → api.uspto.gov
  New query format: string boolean (was JSON q/f/o); header X-API-KEY
  Override via env: PATENTSVIEW_API_URL

Weekly cadence with offset-based pagination.

Source: https://api.uspto.gov/api/v1/patent/applications/search
"""

import hashlib
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# USPTO ODP endpoint (migrated from search.patentsview.org on 2026-03-20)
_DEFAULT_PATENTSVIEW_API = "https://api.uspto.gov/api/v1/patent/applications/search"

# CPC codes relevant to pharmaceutical chemistry
PHARMA_CPC_CODES = ["A61K", "A61P", "C07D"]

# Pagination settings
PAGE_SIZE = 100
MAX_PAGES = 50  # Safety limit


class USPTOCIFetcher(BaseFetcher):
    """Fetcher for USPTO ODP patent API (CI scope)."""

    SOURCE_NAME = "uspto_ci"
    BASE_URL = "https://api.uspto.gov"

    def get_latest_url(self) -> str:
        """Return the USPTO ODP patent search endpoint URL."""
        return os.environ.get("PATENTSVIEW_API_URL", _DEFAULT_PATENTSVIEW_API)

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch pharmaceutical patents from the USPTO ODP API.

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

            q_string = self._build_query(search_terms, since_date)
            records = self._fetch_paginated(q_string, max_pages=max_pages)

            for record in records:
                patent_id = record.get("patent_id")
                if patent_id and patent_id not in seen_ids:
                    seen_ids.add(patent_id)
                    all_records.append(record)

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
        """Read search terms from meta.ci_search_terms."""
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
            logger.warning("Could not read search terms from DB: %s", e)
            return []

    @staticmethod
    def _build_query(search_terms: List[str], since_date: str) -> str:
        """Build a USPTO ODP string boolean query.

        Combines text search terms (OR) with CPC code filtering and date range.

        Args:
            search_terms: List of keyword strings.
            since_date: ISO date string for grantDate lower bound.

        Returns:
            RSQL/boolean query string for the ODP API.
        """
        cpc_terms = " OR ".join(f"{code}*" for code in PHARMA_CPC_CODES)
        text_terms = " OR ".join(f'"{t}"' for t in search_terms)
        return (
            f"(cpcInventionFlat:({cpc_terms}))"
            f" AND (patentTitle:({text_terms}) OR abstractText:({text_terms}))"
            f" AND grantDate:[{since_date} TO *]"
        )

    def _fetch_paginated(
        self, q_string: str, *, max_pages: int = MAX_PAGES
    ) -> List[Dict[str, Any]]:
        """Fetch paginated results from the USPTO ODP API.

        Uses offset-based pagination.

        Args:
            q_string: Boolean query string for the ODP API.
            max_pages: Safety limit for pagination.

        Returns:
            List of normalized patent record dicts.
        """
        all_records: List[Dict[str, Any]] = []
        offset = 0

        for _page in range(1, max_pages + 1):
            payload = {
                "q": q_string,
                "fields": (
                    "patentNumber,patentTitle,abstractText,grantDate,filingDate,"
                    "patentType,inventorName,assigneeEntityName,cpcInventionFlat,"
                    "numberOfClaims"
                ),
                "sort": "grantDate:desc",
                "limit": PAGE_SIZE,
                "offset": offset,
            }

            try:
                response = self.session.post(
                    self.get_latest_url(),
                    json=payload,
                    timeout=60,
                )
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                logger.warning("USPTO ODP request failed at offset %d: %s", offset, e)
                break

            patents = data.get("patents") or data.get("results") or []
            if not patents:
                break

            for patent in patents:
                record = self._normalize_patent(patent)
                if record:
                    all_records.append(record)

            if len(patents) < PAGE_SIZE:
                break

            offset += PAGE_SIZE

        logger.info("Fetched %d patent records from USPTO ODP", len(all_records))
        return all_records

    @staticmethod
    def _normalize_patent(patent: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize a USPTO ODP patent record to the raw.uspto_ci schema.

        Handles both ODP field names (patentNumber, abstractText, etc.) and
        legacy PatentSearch field names (patent_id, patent_abstract, etc.).
        """
        # ODP: patentNumber; legacy: patent_id
        patent_id = patent.get("patentNumber") or patent.get("patent_id")
        if not patent_id:
            return None

        # Inventors: ODP returns inventorName (string/list); legacy used nested objects
        inventors = None
        raw_inventors = patent.get("inventors") or patent.get("inventorName")
        if raw_inventors:
            if isinstance(raw_inventors, list) and raw_inventors and isinstance(raw_inventors[0], dict):
                inventors = [
                    {
                        "name_first": inv.get("inventor_name_first"),
                        "name_last": inv.get("inventor_name_last"),
                    }
                    for inv in raw_inventors
                ]
            else:
                names = raw_inventors if isinstance(raw_inventors, list) else [raw_inventors]
                inventors = [{"name_full": n} for n in names if n]

        # Assignees: ODP uses assigneeEntityName
        assignees = None
        raw_assignees = patent.get("assignees") or patent.get("assigneeEntityName")
        if raw_assignees:
            if isinstance(raw_assignees, list) and raw_assignees and isinstance(raw_assignees[0], dict):
                assignees = [{"organization": asg.get("assignee_organization")} for asg in raw_assignees]
            else:
                names = raw_assignees if isinstance(raw_assignees, list) else [raw_assignees]
                assignees = [{"organization": n} for n in names if n]

        # CPC codes: ODP uses cpcInventionFlat (list of strings); legacy used cpc_current
        cpc_codes = None
        raw_cpcs = patent.get("cpcInventionFlat") or patent.get("cpc_current")
        if isinstance(raw_cpcs, list):
            if raw_cpcs and isinstance(raw_cpcs[0], dict):
                cpc_codes = [c.get("cpc_subgroup_id", "") for c in raw_cpcs]
            else:
                cpc_codes = [str(c) for c in raw_cpcs if c]

        # Dates
        grant_date = patent.get("grantDate") or patent.get("patent_date")
        filing_date = patent.get("filingDate") or (patent.get("application") or {}).get("filing_date")

        # Claims
        claims_count = patent.get("numberOfClaims") or patent.get("patent_num_claims")
        if claims_count is not None:
            try:
                claims_count = int(claims_count)
            except (ValueError, TypeError):
                claims_count = None

        return {
            "patent_id": str(patent_id),
            "title": patent.get("patentTitle") or patent.get("patent_title"),
            "abstract": patent.get("abstractText") or patent.get("patent_abstract"),
            "inventors": inventors,
            "assignees": assignees,
            "filing_date": filing_date,
            "grant_date": grant_date,
            "cpc_codes": cpc_codes,
            "claims_count": claims_count,
        }
