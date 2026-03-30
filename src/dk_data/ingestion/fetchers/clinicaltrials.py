"""ClinicalTrials.gov v2 API Fetcher.

Fetches clinical trial studies from the ClinicalTrials.gov REST API v2.
Results are stored as page-level JSONB blobs in mol_raw.clinicaltrials —
each raw row contains a ``studies`` array of up to PAGE_SIZE studies.

The bronze model (mol_bronze.clinicaltrials) unnests the studies array
using ``jsonb_array_elements(response_body->'studies')``.

API Docs: https://clinicaltrials.gov/data-api/api
Rate limit: 10 req/s (unauthenticated)
"""

import hashlib
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

# API max is 1000; use 200 to keep responses manageable
PAGE_SIZE = 200

# Default cap per run
DEFAULT_MAX_RECORDS = 10_000

# Polite delay between pages (10 req/s limit)
REQUEST_DELAY = 0.15


class ClinicalTrialsFetcher(BaseFetcher):
    """Fetcher for ClinicalTrials.gov study data.

    Pages through the v2 /studies endpoint and returns one dict per page,
    each containing a ``studies`` list (matching the API response shape
    expected by mol_bronze.clinicaltrials).
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

        Keyword Args:
            days_back: Restrict to studies updated in the last N days. Defaults to 30.
            max_records: Maximum study records to fetch across all pages. Defaults to 10000.
            condition: Optional condition/disease filter string.
            intervention: Optional intervention/drug filter string.

        Returns:
            Dict with keys: status, records, record_count, hash.
            ``records`` is a list of page blobs (each with a ``studies`` key),
            not individual studies — the loader inserts one raw row per page.
        """
        days_back: int = int(kwargs.get("days_back", 30))
        max_records: int = int(kwargs.get("max_records", DEFAULT_MAX_RECORDS))
        condition: Optional[str] = kwargs.get("condition")
        intervention: Optional[str] = kwargs.get("intervention")

        try:
            date_str = datetime.utcnow().strftime("%Y-%m-%d")
            from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

            page_blobs, total_studies = self._paginate(
                from_date=from_date,
                max_records=max_records,
                date_str=date_str,
                condition=condition,
                intervention=intervention,
            )

            content_hash = hashlib.md5(
                f"{date_str}:{total_studies}".encode()
            ).hexdigest()

            result = {
                "status": "success",
                "records": page_blobs,
                "record_count": len(page_blobs),
                "hash": content_hash,
                "_total_studies": total_studies,
            }
            self.log_fetch_result({"status": "success", "records": len(page_blobs)})
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

    def _paginate(
        self,
        from_date: str,
        max_records: int,
        date_str: str,
        condition: Optional[str],
        intervention: Optional[str],
    ) -> tuple:
        """Page through the ClinicalTrials.gov v2 API.

        Returns:
            Tuple of (page_blobs, total_studies_fetched).
            page_blobs: list of dicts, each with keys:
                _request_id, _page_number, studies
        """
        page_blobs: List[Dict[str, Any]] = []
        total_studies = 0
        page_token: Optional[str] = None
        page_num = 0

        while total_studies < max_records:
            remaining = max_records - total_studies
            page_size = min(PAGE_SIZE, remaining)

            params: Dict[str, Any] = {
                "pageSize": page_size,
                "format": "json",
                "filter.advanced": f"AREA[LastUpdatePostDate]RANGE[{from_date},MAX]",
            }
            if page_token:
                params["pageToken"] = page_token
            if condition:
                params["query.cond"] = condition
            if intervention:
                params["query.intr"] = intervention

            try:
                data = self.fetch_json(BASE_URL, params=params)
            except Exception as exc:
                logger.warning(
                    "ClinicalTrials page %d fetch failed: %s", page_num, exc
                )
                break

            studies = data.get("studies", [])
            if not studies:
                break

            page_blob = {
                "_request_id": f"ct_v2_{date_str}_page{page_num:05d}",
                "_page_number": page_num,
                "studies": studies,
            }
            page_blobs.append(page_blob)
            total_studies += len(studies)
            page_num += 1

            logger.info(
                "ClinicalTrials: page %d fetched %d studies (total: %d)",
                page_num - 1, len(studies), total_studies,
            )

            page_token = data.get("nextPageToken")
            if not page_token:
                break

            time.sleep(REQUEST_DELAY)

        logger.info(
            "ClinicalTrials pagination complete: %d pages, %d studies",
            len(page_blobs), total_studies,
        )
        return page_blobs, total_studies
