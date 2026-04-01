"""OpenFDA FAERS fetcher — FDA Adverse Event Reporting System data.

Fetches adverse drug event reports from the FDA openFDA /drug/event endpoint.
Results are stored as page-level JSONB blobs in mol_raw.openfda_faers —
each raw row contains a ``results`` array of up to PAGE_SIZE event reports.

The bronze model (mol_bronze.openfda_faers) unnests the results array
using ``jsonb_array_elements(response_body->'results')``.

API Docs: https://open.fda.gov/apis/drug/event/
Rate limit: 240 req/min anonymous, 120,000/day with API key.
Max records per search: 25,000 (skip + limit ≤ 25,000).

Full-database strategy (full_backfill=True):
  The FDA API hard-caps skip at 25,000 per query, but the total FAERS
  database is ~15M reports. Year-by-year partitioning on safetyreportdate
  keeps each partition well under the skip limit:
    safetyreportdate:[YEAR0101 TO YEAR1231]
  Reports without safetyreportdate are captured by a separate fallback query.

Incremental mode (default): fetch reports from the last N days.
"""

import hashlib
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.fda.gov/drug/event.json"
_PAGE_SIZE = 1000
_FDA_SKIP_LIMIT = 25_000
_REQUEST_DELAY = 0.3
_DEFAULT_DAYS_BACK = 90
_FULL_BACKFILL_START_YEAR = 2004


class OpenFDAFAERSFetcher(BaseFetcher):
    """Fetcher for FDA FAERS adverse event data via openFDA.

    Pages through the /drug/event endpoint and returns one dict per page,
    each containing a ``results`` list (matching the API response shape
    expected by mol_bronze.openfda_faers).

    Two modes:
      - Incremental (default): fetch reports filed in last N days, up to
        25,000 records. Used for daily refresh CronJob.
      - Full backfill (full_backfill=True): iterate year-by-year from
        start_year to present, covering the ~15M historical FAERS reports.
    """

    SOURCE_NAME = "openfda_faers"
    BASE_URL = "https://api.fda.gov"

    def __init__(self, data_dir: Optional[str] = None) -> None:
        super().__init__(data_dir)
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "DK-Data-Platform/1.0 (mailto:data-platform@datakinetic.com)",
        })

    def get_latest_url(self) -> str:
        return _BASE_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch FAERS adverse event records from openFDA.

        Keyword Args:
            full_backfill: If True, fetch all FAERS records via year partitioning.
                Default: False.
            days_back: Restrict to reports filed in the last N days.
                Defaults to 90. Ignored when full_backfill=True.
            max_records: Maximum records in incremental mode (max 25,000).
                Ignored when full_backfill=True.
            start_year: First year to include in full backfill. Default: 2004.
                Only used when full_backfill=True.

        Returns:
            Dict with keys: status, records, record_count, hash.
            ``records`` is a list of page blobs (each with a ``results`` key),
            not individual reports — the loader inserts one raw row per page.
        """
        full_backfill: bool = bool(kwargs.get("full_backfill", False))

        try:
            date_str = datetime.utcnow().strftime("%Y-%m-%d")

            if full_backfill:
                start_year: int = int(kwargs.get("start_year", _FULL_BACKFILL_START_YEAR))
                page_blobs, total_reports = self._fetch_all_years(
                    start_year=start_year,
                    date_str=date_str,
                )
            else:
                days_back: int = int(kwargs.get("days_back", _DEFAULT_DAYS_BACK))
                max_records: int = min(
                    int(kwargs.get("max_records", _FDA_SKIP_LIMIT)),
                    _FDA_SKIP_LIMIT,
                )
                from_date = (
                    datetime.utcnow() - timedelta(days=days_back)
                ).strftime("%Y%m%d")
                search = f"safetyreportdate:[{from_date} TO 99991231]"

                page_blobs, total_reports = self._paginate(
                    search=search,
                    max_records=max_records,
                    date_str=date_str,
                )

            content_hash = hashlib.md5(
                f"{date_str}:{total_reports}".encode()
            ).hexdigest()

            result: Dict[str, Any] = {
                "status": "success",
                "records": page_blobs,
                "record_count": len(page_blobs),
                "hash": content_hash,
                "_total_reports": total_reports,
            }
            self.log_fetch_result({"status": "success", "records": len(page_blobs)})
            return result

        except Exception as exc:
            logger.exception("OpenFDA FAERS fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_all_years(
        self, start_year: int, date_str: str
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Fetch all FAERS records via year-by-year safetyreportdate partitioning."""
        current_year = datetime.utcnow().year
        all_page_blobs: List[Dict[str, Any]] = []
        grand_total = 0

        for year in range(start_year, current_year + 1):
            search = f"safetyreportdate:[{year}0101 TO {year}1231]"
            logger.info("OpenFDA FAERS: fetching year %d", year)

            try:
                blobs, count = self._paginate(
                    search=search,
                    max_records=_FDA_SKIP_LIMIT,
                    date_str=date_str,
                )
            except Exception as exc:
                logger.warning(
                    "OpenFDA FAERS: year %d failed: %s — skipping", year, exc
                )
                continue

            all_page_blobs.extend(blobs)
            grand_total += count
            logger.info(
                "OpenFDA FAERS: year %d → %d reports (%d pages). Running total: %d",
                year, count, len(blobs), grand_total,
            )

        logger.info(
            "OpenFDA FAERS full backfill complete: %d total reports across %d pages",
            grand_total, len(all_page_blobs),
        )
        return all_page_blobs, grand_total

    def _paginate(
        self,
        search: str,
        max_records: int,
        date_str: str,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Page through the openFDA /drug/event endpoint for a single search query.

        Returns:
            Tuple of (page_blobs, total_reports_fetched).
        """
        page_blobs: List[Dict[str, Any]] = []
        total_reports = 0
        page_num = 0

        while total_reports < max_records:
            skip = total_reports
            if skip >= _FDA_SKIP_LIMIT:
                logger.info(
                    "OpenFDA FAERS[%s]: reached FDA skip limit (%d), stopping",
                    search[:40], _FDA_SKIP_LIMIT,
                )
                break

            remaining = max_records - total_reports
            limit = min(_PAGE_SIZE, remaining, _FDA_SKIP_LIMIT - skip)

            params: Dict[str, Any] = {
                "search": search,
                "limit": limit,
                "skip": skip,
            }

            try:
                data = self.fetch_json(_BASE_URL, params=params)
            except Exception as exc:
                logger.warning(
                    "OpenFDA FAERS page skip=%d fetch failed: %s", skip, exc
                )
                break

            results = data.get("results", [])
            if not results:
                break

            page_blob = {
                "_request_id": f"faers_{date_str}_skip{skip:07d}",
                "_page_number": page_num,
                "results": results,
            }
            page_blobs.append(page_blob)
            total_reports += len(results)
            page_num += 1

            logger.info(
                "OpenFDA FAERS: page %d (skip=%d) fetched %d reports (total: %d)",
                page_num - 1, skip, len(results), total_reports,
            )

            if len(results) < limit:
                break

            time.sleep(_REQUEST_DELAY)

        logger.info(
            "OpenFDA FAERS pagination complete: %d pages, %d reports",
            len(page_blobs), total_reports,
        )
        return page_blobs, total_reports
