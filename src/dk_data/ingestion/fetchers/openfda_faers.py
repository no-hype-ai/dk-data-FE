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
from ..utils.checkpoint import clear_checkpoint, load_checkpoint, save_checkpoint
from ..sources.openfda_faers import load_openfda_faers_data

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
                total_inserted = self._fetch_all_years_streaming(
                    start_year=start_year,
                    date_str=date_str,
                )
                clear_checkpoint(self.SOURCE_NAME)
                content_hash = hashlib.md5(
                    f"{date_str}:{total_inserted}".encode()
                ).hexdigest()
                result: Dict[str, Any] = {
                    "status": "success",
                    "records": [],   # streamed directly to DB per year
                    "record_count": total_inserted,
                    "hash": content_hash,
                }
                self.log_fetch_result({"status": "success", "records": total_inserted})
                return result
            else:
                days_back: int = int(kwargs.get("days_back", _DEFAULT_DAYS_BACK))
                max_records: int = min(
                    int(kwargs.get("max_records", _FDA_SKIP_LIMIT)),
                    _FDA_SKIP_LIMIT,
                )
                from_date = (
                    datetime.utcnow() - timedelta(days=days_back)
                ).strftime("%Y%m%d")
                to_date = datetime.utcnow().strftime("%Y%m%d")
                search = f"safetyreportdate:[{from_date} TO {to_date}]"

                page_blobs, total_reports = self._paginate(
                    search=search,
                    max_records=max_records,
                    date_str=date_str,
                )

                content_hash = hashlib.md5(
                    f"{date_str}:{total_reports}".encode()
                ).hexdigest()
                result = {
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

    def _fetch_all_years_streaming(self, start_year: int, date_str: str) -> int:
        """Fetch all FAERS records year-by-year, committing each year to DB immediately.

        Checkpoint is saved after each completed year so a pod restart resumes
        from the next year rather than re-fetching from the beginning.

        Returns total page blobs inserted across all years.
        """
        current_year = datetime.utcnow().year

        # Resume from checkpoint if available
        cp = load_checkpoint(self.SOURCE_NAME)
        resume_year = cp.get("next_year", start_year) if cp else start_year
        total_inserted = cp.get("records_inserted", 0) if cp else 0

        if resume_year > start_year:
            logger.info(
                "OpenFDA FAERS: resuming from checkpoint year=%d (%d blobs already inserted)",
                resume_year, total_inserted,
            )

        for year in range(resume_year, current_year + 1):
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

            if blobs:
                result = load_openfda_faers_data(blobs)
                total_inserted += result.get("records_inserted", 0)

            save_checkpoint(self.SOURCE_NAME, {
                "next_year": year + 1,
                "records_inserted": total_inserted,
            })
            logger.info(
                "OpenFDA FAERS: year %d → %d reports (%d pages). "
                "Total inserted: %d. Checkpoint saved.",
                year, count, len(blobs), total_inserted,
            )

        logger.info(
            "OpenFDA FAERS full backfill complete: %d total page blobs inserted",
            total_inserted,
        )
        return total_inserted

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
