"""OpenFDA Device PMA fetcher — Premarket Approvals.

Fetches PMA records from the FDA openFDA /device/pma endpoint.
Results are stored as page-level JSONB blobs in mol_raw.openfda_device_pma.
Total corpus is small (~20K records), so a single full-scan paginated run fits
well within the 25K skip limit. No year-partitioning needed.

API Docs:   https://open.fda.gov/apis/device/pma/
Rate limit: 240 req/min, 120,000/day with API key (reuses OPENFDA_API_KEY).
Max records per search: 25,000 (skip + limit ≤ 25,000).
"""

import hashlib
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from .base import BaseFetcher
from ..sources.openfda_device_pma import load_openfda_device_pma_data

logger = logging.getLogger(__name__)

BASE_URL = "https://api.fda.gov/device/pma.json"
PAGE_SIZE = 100
FDA_SKIP_LIMIT = 25_000
_OPENFDA_API_KEY: Optional[str] = os.getenv("OPENFDA_API_KEY") or None
REQUEST_DELAY = 0.3
DEFAULT_DAYS_BACK = 90


class OpenFDADevicePMAFetcher(BaseFetcher):
    """Fetcher for FDA PMA premarket approvals via openFDA."""

    SOURCE_NAME = "openfda_device_pma"
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
        """Fetch PMA records from openFDA.

        Keyword Args:
            full_backfill: If True, fetch the entire PMA corpus (~20K records).
            days_back:     Restrict to decisions in last N days (default 90).
            max_records:   Cap (default 25,000).
        """
        full_backfill: bool = bool(kwargs.get("full_backfill", False))

        try:
            date_str = datetime.utcnow().strftime("%Y-%m-%d")

            if full_backfill:
                # PMA corpus is small — single paginated full-scan, no date filter.
                search = "_exists_:pma_number"
                max_records = FDA_SKIP_LIMIT
            else:
                days_back: int = int(kwargs.get("days_back", DEFAULT_DAYS_BACK))
                max_records = min(
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
            logger.exception("OpenFDA PMA fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

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
                logger.warning("OpenFDA PMA skip=%d fetch failed: %s", skip, exc)
                break

            results = data.get("results", [])
            if not results:
                break

            page_blob = {
                "_request_id": f"fda_device_pma_{date_str}_skip{skip:07d}",
                "_page_number": page_num,
                "results": results,
            }
            load_result = load_openfda_device_pma_data([page_blob])
            pages_inserted += load_result.get("records_inserted", 0)
            total_records += len(results)
            page_num += 1

            logger.info(
                "OpenFDA PMA: page %d skip=%d fetched %d (total %d, inserted %d)",
                page_num - 1, skip, len(results), total_records, pages_inserted,
            )

            if len(results) < limit:
                break
            time.sleep(REQUEST_DELAY)

        logger.info(
            "OpenFDA PMA pagination complete: %d pages, %d records, %d inserted",
            page_num, total_records, pages_inserted,
        )
        return pages_inserted, total_records
