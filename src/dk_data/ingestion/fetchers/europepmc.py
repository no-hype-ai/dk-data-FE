"""EuropePMC REST API Fetcher.

Feature: 011-datasource-integration
Task: EuropePMC literature source integration

Fetches pharma-relevant publications from Europe PMC using the REST search API
with cursor-based pagination.  Records are stored as-is (raw JSONB) in
mol_raw.europepmc by the loader, so field names here must match the
EuropePMC search API response schema.

API Docs: https://europepmc.org/RestfulWebService#!/Europe32PMC32Articles32RESTful32API
Rate limit: 10 req/s (unauthenticated); use polite pool via email param.

Self-loading with checkpoint/resume:
  Commits to DB and saves a checkpoint every CHECKPOINT_INTERVAL pages so
  a pod restart (OOMKill / timeout) resumes from the last committed offset.
  Memory is O(PAGE_SIZE) at all times.

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

from ..sources.europepmc import load_europepmc_data
from ..utils.checkpoint import clear_checkpoint, load_checkpoint, save_checkpoint
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

# Flush to DB and checkpoint every N pages (100 records/page × 50 = 5000 records per flush)
CHECKPOINT_INTERVAL = 50


class EuropePMCFetcher(BaseFetcher):
    """Fetcher for EuropePMC publications.

    Uses the /search endpoint with cursor-based pagination.
    Results are streamed directly to mol_raw.europepmc with checkpoint/resume.
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
        """Fetch publications from EuropePMC, streaming pages directly to DB.

        Keyword Args:
            query: EuropePMC search query. Defaults to pharma mesh terms.
            days_back: Number of days to look back. Defaults to None (no filter).
            max_records: Maximum records to fetch. Defaults to None (unlimited).
            open_access_only: Filter to open-access only. Defaults to False.

        Returns:
            Dict with keys: status, records (empty — flushed to DB), record_count, hash.
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

            # Resume from checkpoint if available
            cp = load_checkpoint(self.SOURCE_NAME)
            resume_cursor = "*"
            resume_total = 0
            if cp and cp.get("query") == full_query:
                resume_cursor = cp.get("cursor_mark", "*")
                resume_total = cp.get("total_fetched", 0)
                logger.info(
                    "EuropePMC: resuming from checkpoint cursor=%s total=%d",
                    resume_cursor[:30], resume_total,
                )
            elif cp:
                # Query changed (e.g. different days_back) — start fresh
                logger.info("EuropePMC: checkpoint query mismatch, starting fresh")

            logger.info(
                "Fetching EuropePMC publications (days_back=%s, max=%s)",
                days_back, max_records,
            )

            total_fetched = self._stream_to_db(
                full_query,
                max_records=max_records,
                resume_cursor=resume_cursor,
                resume_total=resume_total,
            )

            clear_checkpoint(self.SOURCE_NAME)

            content_hash = hashlib.md5(
                f"{full_query}:{total_fetched}".encode()
            ).hexdigest()

            result = {
                "status": "success",
                "records": [],  # already in DB
                "record_count": total_fetched,
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": total_fetched})
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

    def _stream_to_db(
        self,
        query: str,
        max_records: Optional[int],
        resume_cursor: str = "*",
        resume_total: int = 0,
    ) -> int:
        """Page through EuropePMC and flush each batch directly to DB.

        Saves a checkpoint every CHECKPOINT_INTERVAL pages so the job can
        resume after a pod restart without re-fetching already-committed data.

        Returns:
            Total number of records written to DB this run (including resumed pages
            counted from checkpoint, i.e. the running total).
        """
        cursor_mark = resume_cursor
        total_fetched = resume_total
        url = self.get_latest_url()
        page_buffer: List[Dict[str, Any]] = []
        pages_since_checkpoint = 0

        while max_records is None or total_fetched < max_records:
            page_size = min(
                PAGE_SIZE,
                (max_records - total_fetched) if max_records is not None else PAGE_SIZE,
            )

            params = {
                "query": query,
                "format": "json",
                "pageSize": page_size,
                "cursorMark": cursor_mark,
                "resultType": "core",
            }

            try:
                data = self.fetch_json(url, params=params)
            except Exception as exc:
                logger.warning(
                    "EuropePMC page fetch failed at cursor=%s: %s", cursor_mark, exc
                )
                if cursor_mark == "*" and resume_total == 0:
                    # First page failure on a fresh run — propagate
                    raise
                # Flush remaining buffer before giving up
                if page_buffer:
                    load_europepmc_data(page_buffer)
                    save_checkpoint(self.SOURCE_NAME, {
                        "cursor_mark": cursor_mark,
                        "total_fetched": total_fetched,
                        "query": query,
                    })
                break

            result_list = data.get("resultList", {})
            results = result_list.get("result", [])

            if not results:
                break

            page_buffer.extend(results)
            total_fetched += len(results)
            pages_since_checkpoint += 1

            next_cursor = data.get("nextCursorMark")
            if not next_cursor or next_cursor == cursor_mark:
                break

            cursor_mark = next_cursor

            # Flush buffer and checkpoint every CHECKPOINT_INTERVAL pages
            if pages_since_checkpoint >= CHECKPOINT_INTERVAL:
                load_europepmc_data(page_buffer)
                page_buffer = []
                pages_since_checkpoint = 0
                save_checkpoint(self.SOURCE_NAME, {
                    "cursor_mark": cursor_mark,
                    "total_fetched": total_fetched,
                    "query": query,
                })
                logger.info(
                    "EuropePMC: checkpoint saved cursor=%s total=%d",
                    cursor_mark[:30], total_fetched,
                )

            time.sleep(REQUEST_DELAY)

        # Flush any remaining records
        if page_buffer:
            load_europepmc_data(page_buffer)

        logger.info("EuropePMC streamed %d records to DB", total_fetched)
        return total_fetched
