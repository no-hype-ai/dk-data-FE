"""ClinicalTrials.gov v2 API Fetcher.

Fetches clinical trial studies from the ClinicalTrials.gov REST API v2.
Results are stored as page-level JSONB blobs in mol_raw.clinicaltrials —
each raw row contains a ``studies`` array of up to PAGE_SIZE studies.

The bronze model (mol_bronze.clinicaltrials) unnests the studies array
using ``jsonb_array_elements(response_body->'studies')``.

API Docs: https://clinicaltrials.gov/data-api/api
Rate limit: 10 req/s (unauthenticated)

Self-loading with checkpoint/resume:
  Commits to DB and saves a checkpoint every CHECKPOINT_INTERVAL pages so
  that a pod restart or OOMKill can resume from the last committed page token.
  Checkpoint is cleared on successful completion.
"""

import hashlib
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base import BaseFetcher
from ..utils.checkpoint import clear_checkpoint, load_checkpoint, save_checkpoint
from ..sources.clinicaltrials import load_clinicaltrials_data

logger = logging.getLogger(__name__)

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

# API max is 1000; use 200 to keep responses manageable
PAGE_SIZE = 200

# Default cap per run — None means unlimited (fetch all studies)
DEFAULT_MAX_RECORDS = None

# Polite delay between pages (10 req/s limit)
REQUEST_DELAY = 0.15

# Flush to DB and checkpoint every N pages (200 studies/page × 25 = 5000 studies per flush)
CHECKPOINT_INTERVAL = 25


class ClinicalTrialsFetcher(BaseFetcher):
    """Fetcher for ClinicalTrials.gov study data.

    Pages through the v2 /studies endpoint and streams page blobs directly
    to DB every CHECKPOINT_INTERVAL pages with checkpoint/resume support.
    This keeps memory usage bounded regardless of total result set size.
    """

    SOURCE_NAME = "clinicaltrials"
    BASE_URL = BASE_URL

    def __init__(self, data_dir: Optional[str] = None) -> None:
        super().__init__(data_dir)
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "DK-Data-Platform/1.0 (mailto:data-platform@datakinetic.com)",
        })

    def get_latest_url(self) -> str:
        return BASE_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch clinical trial studies from ClinicalTrials.gov v2.

        Self-loading: streams pages directly to DB with checkpoint/resume.
        Returns records=[] (data is not held in memory).

        Keyword Args:
            days_back: Restrict to studies updated in the last N days. Defaults to None
                (no date filter — fetch all studies). Pass an integer to limit to recent updates.
            max_records: Maximum study records to fetch across all pages. Defaults to None
                (unlimited — fetch entire ClinicalTrials.gov database, ~500K studies).
            condition: Optional condition/disease filter string.
            intervention: Optional intervention/drug filter string.

        Returns:
            Dict with keys: status, records, record_count, hash.
            ``records`` is always [] — data is streamed directly to DB.
        """
        raw_days_back = kwargs.get("days_back", None)
        days_back: Optional[int] = int(raw_days_back) if raw_days_back is not None else None
        raw_max = kwargs.get("max_records", DEFAULT_MAX_RECORDS)
        max_records: Optional[int] = int(raw_max) if raw_max is not None else None
        condition: Optional[str] = kwargs.get("condition")
        intervention: Optional[str] = kwargs.get("intervention")

        try:
            date_str = datetime.utcnow().strftime("%Y-%m-%d")
            from_date = (
                (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
                if days_back is not None else None
            )

            total_pages, total_studies = self._fetch_and_load(
                from_date=from_date,
                max_records=max_records,
                date_str=date_str,
                condition=condition,
                intervention=intervention,
            )

            content_hash = hashlib.md5(
                f"{date_str}:{total_studies}".encode()
            ).hexdigest()

            clear_checkpoint(self.SOURCE_NAME)

            result = {
                "status": "success",
                "records": [],  # streamed directly to DB — not held in memory
                "record_count": total_pages,
                "hash": content_hash,
                "_total_studies": total_studies,
            }
            self.log_fetch_result({"status": "success", "records": total_pages})
            return result

        except Exception as exc:
            logger.exception("ClinicalTrials fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_and_load(
        self,
        from_date: Optional[str],
        max_records: Optional[int],
        date_str: str,
        condition: Optional[str],
        intervention: Optional[str],
    ) -> tuple:
        """Page through the ClinicalTrials.gov v2 API, flushing to DB every CHECKPOINT_INTERVAL pages.

        Resumes from checkpoint if one exists (stores page_token + page_num).

        Returns:
            Tuple of (total_pages_inserted, total_studies_fetched).
        """
        # Resume from checkpoint if available
        cp = load_checkpoint(self.SOURCE_NAME)
        page_token: Optional[str] = cp.get("page_token") if cp else None
        page_num: int = cp.get("page_num", 0) if cp else 0
        total_studies: int = cp.get("total_studies", 0) if cp else 0
        total_pages: int = cp.get("total_pages", 0) if cp else 0

        if cp:
            logger.info(
                "ClinicalTrials: resuming from checkpoint page=%d total_studies=%d",
                page_num, total_studies,
            )

        page_buffer: List[Dict[str, Any]] = []
        pages_since_checkpoint = 0

        while max_records is None or total_studies < max_records:
            remaining = (max_records - total_studies) if max_records is not None else PAGE_SIZE
            page_size = min(PAGE_SIZE, remaining)

            params: Dict[str, Any] = {
                "pageSize": page_size,
                "format": "json",
            }
            if from_date:
                params["filter.advanced"] = f"AREA[LastUpdatePostDate]RANGE[{from_date},MAX]"
            if page_token:
                params["pageToken"] = page_token
            if condition:
                params["query.cond"] = condition
            if intervention:
                params["query.intr"] = intervention

            try:
                data = self.fetch_json(BASE_URL, params=params)
            except Exception as exc:
                logger.error(
                    "ClinicalTrials page %d fetch failed: %s", page_num, exc
                )
                # Flush buffer and save checkpoint before giving up
                if page_buffer:
                    load_clinicaltrials_data(page_buffer)
                    total_pages += len(page_buffer)
                    page_buffer = []
                save_checkpoint(self.SOURCE_NAME, {
                    "page_token": page_token,
                    "page_num": page_num,
                    "total_studies": total_studies,
                    "total_pages": total_pages,
                    "from_date": from_date,
                })
                raise

            studies = data.get("studies", [])
            if not studies:
                break

            page_blob = {
                "_request_id": f"ct_v2_{date_str}_page{page_num:05d}",
                "_page_number": page_num,
                "studies": studies,
            }
            page_buffer.append(page_blob)
            total_studies += len(studies)
            page_num += 1
            pages_since_checkpoint += 1

            logger.info(
                "ClinicalTrials: page %d fetched %d studies (total: %d)",
                page_num - 1, len(studies), total_studies,
            )

            page_token = data.get("nextPageToken")

            # Flush to DB and checkpoint every CHECKPOINT_INTERVAL pages
            if pages_since_checkpoint >= CHECKPOINT_INTERVAL:
                load_clinicaltrials_data(page_buffer)
                total_pages += len(page_buffer)
                page_buffer = []
                pages_since_checkpoint = 0
                save_checkpoint(self.SOURCE_NAME, {
                    "page_token": page_token,
                    "page_num": page_num,
                    "total_studies": total_studies,
                    "total_pages": total_pages,
                    "from_date": from_date,
                })
                logger.info(
                    "ClinicalTrials: checkpoint saved page=%d total_studies=%d",
                    page_num, total_studies,
                )

            if not page_token:
                break

            time.sleep(REQUEST_DELAY)

        # Flush remaining buffer
        if page_buffer:
            load_clinicaltrials_data(page_buffer)
            total_pages += len(page_buffer)

        logger.info(
            "ClinicalTrials pagination complete: %d pages, %d studies",
            total_pages, total_studies,
        )
        return total_pages, total_studies
