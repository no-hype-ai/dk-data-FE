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

from ..sources.nih_reporter import load_nih_reporter_data
from ..utils.checkpoint import clear_checkpoint, load_checkpoint, save_checkpoint
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
# NIH Reporter Projects API hard-stops at offset 14,999 (15,000 records max per query).
# Publications API hard-stops at offset 9,999 (10,000 records max per query).
# The date-range filter (project_start_date) keeps result sets well under this ceiling.
# Setting this to 50,000 would never trigger on a single unfiltered query.
MAX_RECORDS = 15_000  # matches Projects API hard ceiling

# NIH Reporter docs recommend ~1 req/s to avoid throttling.
REQUEST_DELAY = 1.1  # seconds between paginated POST requests


class NIHReporterFetcher(BaseFetcher):
    SOURCE_NAME = "nih_reporter"
    BASE_URL = NIH_REPORTER_API

    def fetch(self, days_back: int = None, **kwargs) -> Dict[str, Any]:
        """Fetch NIH Reporter projects, streaming pages directly to DB.

        Args:
            days_back: Look back this many days for project start dates.
                       Defaults to None — full backfill mode iterates year by year
                       from 1985 to present (bypasses the 15K per-query API ceiling).
                       Pass an integer (e.g. 30) for incremental daily runs.

        Returns:
            Dict with keys: status, records (empty — flushed to DB), record_count, hash.
        """
        if days_back is None:
            return self._fetch_full_backfill()

        since_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        today = datetime.utcnow().strftime("%Y-%m-%d")
        try:
            total = self._stream_date_range(since_date, today)
        except Exception as e:
            logger.error("NIH Reporter fetch failed: %s", e)
            return {"status": "failed", "records": [], "record_count": 0, "hash": None, "error": str(e)}
        logger.info(
            "NIH Reporter fetched %d projects (days_back=%d, since=%s)",
            total, days_back, since_date,
        )
        return {"status": "success", "records": [], "record_count": total, "hash": None}

    def _fetch_full_backfill(self) -> Dict[str, Any]:
        """Fetch all NIH Reporter projects by iterating year by year from 1985.

        Checkpoints after each year so pod restarts resume from the next year.
        Memory is O(PAGE_SIZE) at all times.
        """
        current_year = datetime.utcnow().year
        grand_total = 0

        # Resume from checkpoint if available
        cp = load_checkpoint(self.SOURCE_NAME)
        start_year = 1985
        if cp:
            start_year = cp.get("next_year", 1985)
            grand_total = cp.get("total_fetched", 0)
            logger.info(
                "NIH Reporter: resuming from checkpoint year=%d total=%d",
                start_year, grand_total,
            )

        for year in range(start_year, current_year + 1):
            from_date = f"{year}-01-01"
            to_date = f"{year}-12-31"
            logger.info("NIH Reporter: fetching year %d", year)

            year_count = self._stream_date_range(from_date, to_date)
            grand_total += year_count

            logger.info(
                "NIH Reporter: year %d → %d projects (running total: %d)",
                year, year_count, grand_total,
            )

            # Checkpoint after each year — resume from next year on restart
            save_checkpoint(self.SOURCE_NAME, {
                "next_year": year + 1,
                "total_fetched": grand_total,
            })

        clear_checkpoint(self.SOURCE_NAME)
        logger.info("NIH Reporter full backfill complete: %d total projects", grand_total)
        return {"status": "success", "records": [], "record_count": grand_total, "hash": None}

    def _stream_date_range(self, from_date: str, to_date: str) -> int:
        """Fetch all projects within a date range, writing each page directly to DB.

        Returns:
            Number of projects fetched and written.
        """
        payload = {
            "criteria": {
                "project_start_date": {
                    "from_date": from_date,
                    "to_date": to_date,
                }
            },
            "limit": PAGE_SIZE,
            "offset": 0,
        }
        total = 0

        while True:
            try:
                resp = self.session.post(self.BASE_URL, json=payload, timeout=60)
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
                logger.error("NIH Reporter fetch error at offset %d: %s", payload["offset"], e)
                if payload["offset"] == 0:
                    # First page failure — propagate so fetch() can return status='failed'
                    raise
                break

            results: List[Dict[str, Any]] = data.get("results", [])
            if not results:
                break

            # Flush page immediately to DB — bounded memory
            load_nih_reporter_data(results)
            total += len(results)

            api_total = data.get("meta", {}).get("total", 0)
            next_offset = payload["offset"] + PAGE_SIZE
            if next_offset >= api_total or next_offset >= MAX_RECORDS:
                break

            payload["offset"] = next_offset
            time.sleep(REQUEST_DELAY)

        return total

    def get_latest_url(self) -> str:
        return self.BASE_URL
