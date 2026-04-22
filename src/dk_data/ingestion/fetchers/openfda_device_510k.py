"""OpenFDA Device 510(k) fetcher — Premarket Notifications.

Fetches 510(k) clearance records from the FDA openFDA /device/510k endpoint.
Results are stored as page-level JSONB blobs in mol_raw.openfda_device_510k —
each raw row contains a ``results`` array of up to PAGE_SIZE device records.

The bronze model (mol_bronze.openfda_device_510k) unnests the results array
using ``jsonb_array_elements(response_body->'results')``.

API Docs:   https://open.fda.gov/apis/device/510k/
Rate limit: 240 req/min, 120,000 req/day with API key (reuses OPENFDA_API_KEY).
Max records per search: 25,000 (skip + limit ≤ 25,000).

Full-database strategy (full_backfill=True):
  Year-partitioned on decision_date. 510(k) dates back to 1976, but meaningful
  modern volumes begin around 2000. Each year typically has <15K decisions —
  well under the skip limit. Total corpus ~250K records.

Incremental mode (default): fetch clearances decided in the last N days.
"""

import hashlib
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseFetcher
from ..utils.checkpoint import clear_checkpoint, load_checkpoint, save_checkpoint
from ..sources.openfda_device_510k import load_openfda_device_510k_data

logger = logging.getLogger(__name__)

BASE_URL = "https://api.fda.gov/device/510k.json"
PAGE_SIZE = 100
FDA_SKIP_LIMIT = 25_000
_OPENFDA_API_KEY: Optional[str] = os.getenv("OPENFDA_API_KEY") or None
REQUEST_DELAY = 0.3
DEFAULT_DAYS_BACK = 90
FULL_BACKFILL_START_YEAR = 2000


class OpenFDADevice510kFetcher(BaseFetcher):
    """Fetcher for FDA Device 510(k) premarket notifications via openFDA."""

    SOURCE_NAME = "openfda_device_510k"
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
        """Fetch 510(k) clearance records from openFDA.

        Keyword Args:
            full_backfill: If True, year-partition 2000 → current. Default: False.
            days_back:     Restrict to decisions in last N days (default 90).
            max_records:   Cap incremental pull (default 25,000).
            start_year:    First year for full backfill (default 2000).
        """
        full_backfill: bool = bool(kwargs.get("full_backfill", False))

        try:
            date_str = datetime.utcnow().strftime("%Y-%m-%d")

            if full_backfill:
                start_year: int = int(kwargs.get("start_year", FULL_BACKFILL_START_YEAR))
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
                    "records": [],
                    "record_count": total_inserted,
                    "hash": content_hash,
                }
                self.log_fetch_result({"status": "success", "records": total_inserted})
                return result

            days_back: int = int(kwargs.get("days_back", DEFAULT_DAYS_BACK))
            max_records: int = min(
                int(kwargs.get("max_records", FDA_SKIP_LIMIT)),
                FDA_SKIP_LIMIT,
            )
            from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y%m%d")
            to_date = datetime.utcnow().strftime("%Y%m%d")
            search = f"decision_date:[{from_date} TO {to_date}]"

            pages_inserted, total = self._paginate_and_load(
                search=search, max_records=max_records, date_str=date_str,
            )
            content_hash = hashlib.md5(f"{date_str}:{total}".encode()).hexdigest()
            result = {
                "status": "success",
                "records": [],
                "record_count": total,
                "hash": content_hash,
                "_pages_inserted": pages_inserted,
            }
            self.log_fetch_result({"status": "success", "records": total})
            return result

        except Exception as exc:
            logger.exception("OpenFDA 510k fetch failed: %s", exc)
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
        current_year = datetime.utcnow().year
        cp = load_checkpoint(self.SOURCE_NAME)
        resume_year = cp.get("next_year", start_year) if cp else start_year
        total_inserted = cp.get("records_inserted", 0) if cp else 0

        if resume_year > start_year:
            logger.info(
                "OpenFDA 510k: resuming year=%d (%d already inserted)",
                resume_year, total_inserted,
            )

        for year in range(resume_year, current_year + 1):
            search = f"decision_date:[{year}0101 TO {year}1231]"
            logger.info("OpenFDA 510k: fetching year %d", year)
            try:
                year_inserted, count = self._paginate_and_load(
                    search=search, max_records=FDA_SKIP_LIMIT, date_str=date_str,
                )
            except Exception as exc:
                logger.warning("OpenFDA 510k: year %d failed: %s — skipping", year, exc)
                continue
            total_inserted += year_inserted
            save_checkpoint(self.SOURCE_NAME, {
                "next_year": year + 1,
                "records_inserted": total_inserted,
            })
            logger.info(
                "OpenFDA 510k: year %d → %d records, %d pages inserted (total %d)",
                year, count, year_inserted, total_inserted,
            )

        logger.info("OpenFDA 510k full backfill complete: %d pages", total_inserted)
        return total_inserted

    def _paginate_and_load(
        self, search: str, max_records: int, date_str: str,
    ) -> Tuple[int, int]:
        pages_inserted = 0
        total_records = 0
        page_num = 0

        while total_records < max_records:
            skip = total_records
            if skip >= FDA_SKIP_LIMIT:
                break
            remaining = max_records - total_records
            limit = min(PAGE_SIZE, remaining, FDA_SKIP_LIMIT - skip)

            params: Dict[str, Any] = {
                "search": search, "limit": limit, "skip": skip,
            }
            if _OPENFDA_API_KEY:
                params["api_key"] = _OPENFDA_API_KEY

            try:
                data = self.fetch_json(BASE_URL, params=params)
            except Exception as exc:
                logger.warning("OpenFDA 510k skip=%d fetch failed: %s", skip, exc)
                break

            results = data.get("results", [])
            if not results:
                break

            page_blob = {
                "_request_id": f"fda_device_510k_{date_str}_skip{skip:07d}",
                "_page_number": page_num,
                "results": results,
            }
            load_result = load_openfda_device_510k_data([page_blob])
            pages_inserted += load_result.get("records_inserted", 0)
            total_records += len(results)
            page_num += 1

            logger.info(
                "OpenFDA 510k: page %d skip=%d fetched %d records (total %d, inserted %d)",
                page_num - 1, skip, len(results), total_records, pages_inserted,
            )

            if len(results) < limit:
                break
            time.sleep(REQUEST_DELAY)

        logger.info(
            "OpenFDA 510k pagination complete: %d pages, %d records, %d inserted",
            page_num, total_records, pages_inserted,
        )
        return pages_inserted, total_records
