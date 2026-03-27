"""NIH RePORTER grants API fetcher — incremental by project_start_date.

Feature: 019-cms-puf-platform-reconciliation

API: POST https://api.reporter.nih.gov/v2/projects/search
No authentication required. Rate limit: ~1 req/s recommended.

Incremental strategy: filter by project_start_date (last N days) on each run.
The ON CONFLICT DO NOTHING in the loader makes repeated runs idempotent.

Fixed (019): date_added_filter is not a valid NIH Reporter v2 criteria key.
  Replaced with project_dates filter (start_date range) which is the correct
  incremental filter for recently funded/modified projects.
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

from .base import BaseFetcher

logger = logging.getLogger(__name__)

try:
    from dk_data.observability.metrics import record_api_request, record_rate_limit_rejection
    _METRICS_AVAILABLE = True
except ImportError:
    _METRICS_AVAILABLE = False
    def record_api_request(*a, **kw): pass  # type: ignore
    def record_rate_limit_rejection(*a, **kw): pass  # type: ignore

NIH_REPORTER_API = "https://api.reporter.nih.gov/v2/projects/search"
PAGE_SIZE = 500
MAX_RECORDS = 50000  # safety cap

# NIH Reporter docs recommend ~1 req/s to avoid throttling.
REQUEST_DELAY = 1.1  # seconds between paginated POST requests


class NIHReporterFetcher(BaseFetcher):
    SOURCE_NAME = "nih_reporter"
    BASE_URL = NIH_REPORTER_API

    def fetch(self, days_back: int = 30, **kwargs) -> Dict[str, Any]:
        """Fetch NIH Reporter projects with a start-date filter.

        Args:
            days_back: Look back this many days from today for project start dates.
                       Defaults to 30. Use a larger value (e.g. 365) for backfills.

        Returns:
            Dict with keys: status, records (list of raw API result dicts), hash.
        """
        since_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        today = datetime.utcnow().strftime("%Y-%m-%d")

        payload = {
            "criteria": {
                # project_dates is the correct NIH Reporter v2 incremental filter
                "project_start_date": {
                    "from_date": since_date,
                    "to_date": today,
                }
            },
            "limit": PAGE_SIZE,
            "offset": 0,
        }

        all_projects: List[Dict] = []

        while True:
            try:
                resp = self.session.post(
                    self.BASE_URL,
                    json=payload,
                    timeout=60,
                )
                resp.raise_for_status()
                data = resp.json()
                record_api_request(self.SOURCE_NAME, "success")
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "Too Many Requests" in err_str:
                    record_rate_limit_rejection(self.SOURCE_NAME)
                    record_api_request(self.SOURCE_NAME, "rate_limited")
                else:
                    record_api_request(self.SOURCE_NAME, "error")
                logger.error(
                    "NIH Reporter fetch error at offset %d: %s",
                    payload["offset"], e,
                )
                return {"status": "failed", "records": [], "hash": None, "error": err_str}

            results = data.get("results", [])
            if not results:
                break

            all_projects.extend(results)

            total = data.get("meta", {}).get("total", 0)
            next_offset = payload["offset"] + PAGE_SIZE
            if next_offset >= total or next_offset >= MAX_RECORDS:
                break

            payload["offset"] = next_offset
            time.sleep(REQUEST_DELAY)

        logger.info(
            "NIH Reporter fetched %d projects (days_back=%d, since=%s)",
            len(all_projects), days_back, since_date,
        )
        return {"status": "success", "records": all_projects, "hash": None}

    def get_latest_url(self) -> str:
        return self.BASE_URL
