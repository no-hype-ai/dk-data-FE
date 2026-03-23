"""Europe PMC Data Fetcher.

Feature: europepmc-integration
Task: Bulk fetcher for scheduled cron ingestion

Fetches publications from Europe PMC REST API (https://europepmc.org/RestfulWebService).
Supports:
  - Scheduled bulk ingestion of pharmaceutical literature (cron job)
  - Per-molecule triggered retrieval (via ingest/{source} endpoint)

Key advantages over PubMed/OpenAlex:
  - Full-text access for 10.2M+ PMC articles
  - Biomedical entity annotations (genes, diseases, chemicals)
  - NCT number → publication cross-links
  - Preprint coverage (bioRxiv, medRxiv)
  - 33M+ total publications including European research

Rate limit: 10 requests/second (no auth required).
"""

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Default pharma-relevant query for scheduled bulk ingestion
DEFAULT_BULK_QUERY = (
    "(MESH_TERM:\"Drug Therapy\" OR MESH_TERM:\"Clinical Trial\" OR "
    "MESH_TERM:\"Antineoplastic Agents\" OR MESH_TERM:\"Antibodies, Monoclonal\" OR "
    "MESH_TERM:\"Immunotherapy\") AND LANG:eng"
)


class EuropePMCFetcher(BaseFetcher):
    """Fetcher for Europe PMC literature via REST API."""

    SOURCE_NAME = "europepmc"
    BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"

    # Max publications per page (API limit)
    PAGE_SIZE = 100

    # Hard cap for bulk scheduled runs
    MAX_BULK_RESULTS = 5000

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)
        # Rate limit: 10 req/s
        self._request_delay = 0.11

    # ------------------------------------------------------------------
    # BaseFetcher abstract interface
    # ------------------------------------------------------------------

    def get_latest_url(self) -> str:
        """Return the EuropePMC search endpoint URL."""
        return f"{self.BASE_URL}/search"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch publications from Europe PMC.

        Keyword Args:
            drug_name: Drug or molecule name to search (for per-molecule ingest).
            query: Custom EuropePMC Lucene query. Overrides drug_name if provided.
            days_back: For scheduled runs — limit to publications from N days ago.
            max_results: Hard cap on total results. Defaults to MAX_BULK_RESULTS.
            open_access_only: Only fetch open-access publications.
            source_filter: Europe PMC source filter (MED, PMC, PPR, etc.).

        Returns:
            Dict with keys: status, records, hash, error (on failure).
        """
        drug_name: Optional[str] = kwargs.get("drug_name")
        custom_query: Optional[str] = kwargs.get("query")
        days_back: Optional[int] = kwargs.get("days_back")
        max_results: int = kwargs.get("max_results", self.MAX_BULK_RESULTS)
        open_access_only: bool = kwargs.get("open_access_only", False)
        source_filter: Optional[str] = kwargs.get("source_filter")

        # Build query
        if custom_query:
            query = custom_query
        elif drug_name:
            query = self._build_drug_query(drug_name, open_access_only, source_filter)
        else:
            query = DEFAULT_BULK_QUERY
            if days_back:
                query += f" AND FIRST_PDATE:[{self._days_ago(days_back)} TO *]"

        manifest = self.load_manifest()
        resume_cursor: Optional[str] = (
            manifest.get("last_cursor") if kwargs.get("resume", True) else None
        )

        try:
            records = self._search_paginated(query, max_results=max_results,
                                             resume_cursor=resume_cursor)

            content_hash = hashlib.md5(
                ",".join(r.get("id", r.get("pmid", "")) for r in records).encode()
            ).hexdigest()

            self.save_manifest(
                last_run_at=datetime.now(timezone.utc).isoformat(),
                last_run_status="completed",
                total_records_fetched=len(records),
                last_content_hash=content_hash,
                last_cursor=None,
            )

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "hash": content_hash,
            }
            self.log_fetch_result({**result, "records": len(records)})
            return result

        except Exception as e:
            logger.exception(f"[europepmc] Fetch failed: {e}")
            self.save_manifest(last_run_status="interrupted")
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

    def _build_drug_query(
        self,
        drug_name: str,
        open_access_only: bool = False,
        source_filter: Optional[str] = None,
    ) -> str:
        """Build an EuropePMC query for a specific drug/molecule."""
        # Use quoted phrase for exact matching, plus synonyms via drug name
        query = f'"{drug_name}"'
        if open_access_only:
            query += " AND OPEN_ACCESS:y"
        if source_filter:
            query += f" AND SRC:{source_filter}"
        return query

    def _search_paginated(
        self,
        query: str,
        max_results: int = 1000,
        resume_cursor: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search EuropePMC with cursor-based pagination.

        Returns raw API result dicts (normalized by bronze SQLMesh model).
        """
        all_records: List[Dict[str, Any]] = []
        cursor_mark = resume_cursor or "*"
        fetched = 0

        while fetched < max_results:
            page_size = min(self.PAGE_SIZE, max_results - fetched)
            params = {
                "query": query,
                "format": "json",
                "pageSize": page_size,
                "resultType": "core",  # Full metadata including abstract
                "cursorMark": cursor_mark,
                "sort": "P_PDATE_D",  # Newest first
            }

            logger.debug(
                f"[europepmc] Fetching cursor={cursor_mark[:20]} "
                f"fetched={fetched}/{max_results}"
            )

            response = self.session.get(
                f"{self.BASE_URL}/search",
                params=params,
                timeout=30,
            )
            response.raise_for_status()

            data = response.json()
            results = data.get("resultList", {}).get("result", [])

            if not results:
                break

            all_records.extend(results)
            fetched += len(results)

            next_cursor = data.get("nextCursorMark")
            if not next_cursor or next_cursor == cursor_mark:
                break

            cursor_mark = next_cursor
            # Persist cursor so an interrupted run can resume
            self.save_manifest(last_cursor=cursor_mark, last_run_status="in_progress")
            time.sleep(self._request_delay)

        logger.info(f"[europepmc] Fetched {len(all_records)} publications")
        return all_records

    @staticmethod
    def _days_ago(days: int) -> str:
        """Return ISO date string N days ago (for EuropePMC date filter)."""
        from datetime import date, timedelta
        return (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
