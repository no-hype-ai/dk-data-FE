"""OpenFDA Drug Labels Fetcher.

Fetches drug label (SPL) records from the FDA openFDA API.
Results are stored as page-level JSONB blobs in mol_raw.openfda_labels —
each raw row contains a ``results`` array of up to PAGE_SIZE labels.

The bronze model (mol_bronze.openfda_labels) unnests the results array
using ``jsonb_array_elements(response_body->'results')``.

API Docs: https://open.fda.gov/apis/drug/label/
Rate limit: 240 req/min (with or without API key; API key increases daily cap to 120,000 req/day vs 1,000/day anonymous)
Max records per search: 25 000 (skip + limit ≤ 25 000)

Full-database strategy (full_backfill=True):
  The FDA API hard-caps skip at 25 000 per query, but the total SPL label
  database is ~170-200k documents. Year-by-year partitioning on effective_time
  keeps each partition well under the skip limit:
    effective_time:[20000101 TO 20001231] → iterate from 2000 to current year
  Each year typically has <25k new/updated labels, so no partition hits the cap.
  Duplicates across years (re-issued labels) are handled at the bronze layer
  via set_id deduplication in the SQLMesh model.
"""

import hashlib
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from ..sources.openfda_labels import load_openfda_labels_data
from ..utils.checkpoint import clear_checkpoint, load_checkpoint, save_checkpoint
from .base import BaseFetcher

logger = logging.getLogger(__name__)

BASE_URL = "https://api.fda.gov/drug/label.json"

# FDA openFDA API hard cap per page
PAGE_SIZE = 100

# FDA limits total accessible records to 25 000 per search query
FDA_SKIP_LIMIT = 25_000

# Default cap per run (incremental/daily mode)
DEFAULT_MAX_RECORDS = 5_000

# Polite delay between pages
REQUEST_DELAY = 0.1

# First year FDA SPL labels are available in meaningful quantity
_FULL_BACKFILL_START_YEAR = 2000


class OpenFDALabelsFetcher(BaseFetcher):
    """Fetcher for FDA drug label (SPL) data via openFDA.

    Pages through the /drug/label endpoint and returns one dict per page,
    each containing a ``results`` list (matching the API response shape
    expected by mol_bronze.openfda_labels).

    Two modes:
      - Incremental (default): fetch labels updated in last N days, up to
        DEFAULT_MAX_RECORDS. Used for daily refresh CronJob.
      - Full backfill (full_backfill=True): iterate year-by-year from 2000
        to present, fetching all ~170-200k SPL label documents. Deduplication
        of re-issued labels is handled at the bronze SQLMesh model layer.
    """

    SOURCE_NAME = "openfda_labels"
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
        """Fetch drug label records from openFDA.

        Keyword Args:
            full_backfill: If True, fetch all SPL labels via year partitioning
                (ignores days_back, max_records, search). Default: False.
            days_back: Restrict to labels with effective_time updated in the
                last N days. Defaults to 90. Ignored when full_backfill=True.
            max_records: Maximum label records to fetch in incremental mode.
                Defaults to 5000. Ignored when full_backfill=True.
            search: Raw openFDA search query string. If provided, overrides
                the date-based filter. Ignored when full_backfill=True.
            start_year: First year to include in full backfill. Default: 2000.
                Only used when full_backfill=True.

        Returns:
            Dict with keys: status, records, record_count, hash.
            ``records`` is a list of page blobs (each with a ``results`` key),
            not individual labels — the loader inserts one raw row per page.
        """
        full_backfill: bool = bool(kwargs.get("full_backfill", True))  # default: full backfill

        try:
            date_str = datetime.utcnow().strftime("%Y-%m-%d")

            if full_backfill:
                start_year: int = int(kwargs.get("start_year", _FULL_BACKFILL_START_YEAR))
                total_labels = self._stream_all_years(
                    start_year=start_year,
                    date_str=date_str,
                )
            else:
                days_back: int = int(kwargs.get("days_back", 90))
                max_records: int = min(
                    int(kwargs.get("max_records", DEFAULT_MAX_RECORDS)),
                    FDA_SKIP_LIMIT,
                )
                search: Optional[str] = kwargs.get("search")

                if not search:
                    from_date = (
                        datetime.utcnow() - timedelta(days=days_back)
                    ).strftime("%Y%m%d")
                    search = f"effective_time:[{from_date} TO 99991231]"

                _, total_labels = self._paginate(
                    search=search,
                    max_records=max_records,
                    date_str=date_str,
                    stream_to_db=True,
                )

            content_hash = hashlib.md5(
                f"{date_str}:{total_labels}".encode()
            ).hexdigest()

            result = {
                "status": "success",
                "records": [],  # already in DB
                "record_count": total_labels,
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": total_labels})
            return result

        except Exception as exc:
            logger.exception("OpenFDA Labels fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _stream_all_years(self, start_year: int, date_str: str) -> int:
        """Stream all SPL labels to DB via year-by-year partitioning with checkpoint/resume.

        Each year issues its own paginated sequence with
        ``effective_time:[YEAR0101 TO YEAR1231]``. Pages are written directly to DB
        as they arrive — memory is O(PAGE_SIZE) at all times.

        Args:
            start_year: First calendar year to fetch.
            date_str: ISO date string used for request ID tagging.

        Returns:
            Total label count written.
        """
        current_year = datetime.utcnow().year
        grand_total = 0

        # Resume from checkpoint if available
        cp = load_checkpoint(self.SOURCE_NAME)
        resume_year = start_year
        if cp:
            resume_year = cp.get("next_year", start_year)
            grand_total = cp.get("total_labels", 0)
            logger.info(
                "OpenFDA Labels: resuming from checkpoint year=%d total=%d",
                resume_year, grand_total,
            )

        for year in range(resume_year, current_year + 1):
            search = f"effective_time:[{year}0101 TO {year}1231]"
            logger.info("OpenFDA Labels: fetching year %d", year)

            try:
                _, count = self._paginate(
                    search=search,
                    max_records=FDA_SKIP_LIMIT,
                    date_str=date_str,
                    stream_to_db=True,
                )
            except Exception as exc:
                logger.warning("OpenFDA Labels: year %d failed: %s — skipping", year, exc)
                continue

            grand_total += count
            logger.info(
                "OpenFDA Labels: year %d → %d labels. Running total: %d",
                year, count, grand_total,
            )

            # Checkpoint after each year
            save_checkpoint(self.SOURCE_NAME, {
                "next_year": year + 1,
                "total_labels": grand_total,
            })

        clear_checkpoint(self.SOURCE_NAME)
        logger.info(
            "OpenFDA Labels full backfill complete: %d total labels",
            grand_total,
        )
        return grand_total

    def _paginate(
        self,
        search: str,
        max_records: int,
        date_str: str,
        stream_to_db: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Page through the openFDA drug/label endpoint for a single search query.

        Returns:
            Tuple of (page_blobs, total_labels_fetched).
        """
        page_blobs: List[Dict[str, Any]] = []
        total_labels = 0
        page_num = 0

        while total_labels < max_records:
            skip = total_labels
            if skip >= FDA_SKIP_LIMIT:
                logger.info(
                    "OpenFDA Labels[%s]: reached FDA skip limit (%d), stopping",
                    search[:40], FDA_SKIP_LIMIT,
                )
                break

            remaining = max_records - total_labels
            limit = min(PAGE_SIZE, remaining, FDA_SKIP_LIMIT - skip)

            params: Dict[str, Any] = {
                "search": search,
                "limit": limit,
                "skip": skip,
            }

            try:
                data = self.fetch_json(BASE_URL, params=params)
            except Exception as exc:
                logger.warning(
                    "OpenFDA Labels page skip=%d fetch failed: %s", skip, exc
                )
                break

            results = data.get("results", [])
            if not results:
                break

            page_blob = {
                "_request_id": f"fda_labels_{date_str}_skip{skip:07d}",
                "_page_number": page_num,
                "results": results,
            }
            if stream_to_db:
                load_openfda_labels_data([page_blob])
            else:
                page_blobs.append(page_blob)
            total_labels += len(results)
            page_num += 1

            logger.info(
                "OpenFDA Labels: page %d (skip=%d) fetched %d labels (total: %d)",
                page_num - 1, skip, len(results), total_labels,
            )

            # Stop if we got fewer than requested (last page)
            if len(results) < limit:
                break

            time.sleep(REQUEST_DELAY)

        logger.info(
            "OpenFDA Labels pagination complete: %d pages, %d labels",
            len(page_blobs), total_labels,
        )
        return page_blobs, total_labels
