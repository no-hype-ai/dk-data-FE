"""CMS Open Payments (Sunshine Act) fetcher.

Uses the openpaymentsdata.cms.gov DKAN API (separate portal from data.cms.gov).
Most recent dataset: 2024 General Payment Data
UUID: e6b17c6a-2534-4207-a4a1-6746a14911ff
API: https://openpaymentsdata.cms.gov/api/1/datastore/query/{uuid}/0

The DKAN datastore query endpoint supports offset/limit pagination.
Response shape: {"results": [...], "count": N, "schema": {...}}
"""
import csv
import logging
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_OPEN_PAYMENTS_API = "https://openpaymentsdata.cms.gov/api/1/datastore/query"
_PAGE_SIZE = 500

# Most-recent published year — 2024 General Payment Data
_DATASET_UUID = "e6b17c6a-2534-4207-a4a1-6746a14911ff"


class CMSOpenPaymentsFetcher(BaseFetcher):
    SOURCE_NAME = "cms_open_payments"
    DATASET_UUID = _DATASET_UUID

    def get_latest_url(self) -> str:
        return f"{_OPEN_PAYMENTS_API}/{self.DATASET_UUID}/0"

    def _fetch_open_payments_to_csv(
        self, max_records: Optional[int] = None
    ) -> Tuple[Optional[str], int]:
        """Stream DKAN datastore records page-by-page to a temp CSV.

        Returns (csv_path, total_count) or (None, 0) if empty.
        """
        api_url = f"{_OPEN_PAYMENTS_API}/{self.DATASET_UUID}/0"
        total_count = 0
        offset = 0
        tmp = None
        writer = None

        logger.info("[%s] Streaming from openpaymentsdata.cms.gov: %s", self.SOURCE_NAME, api_url)

        try:
            while True:
                remaining = None if max_records is None else max_records - total_count
                if remaining is not None and remaining <= 0:
                    break
                page_size = _PAGE_SIZE if remaining is None else min(_PAGE_SIZE, remaining)

                resp = self.session.get(
                    api_url,
                    params={"offset": offset, "limit": page_size, "keys": "true"},
                    timeout=60,
                )
                resp.raise_for_status()
                data = resp.json()

                page: List[Dict[str, Any]] = data.get("results", [])
                if not page:
                    break

                if writer is None:
                    tmp = tempfile.NamedTemporaryFile(
                        mode="w",
                        suffix=".csv",
                        prefix=f"cms_{self.SOURCE_NAME}_",
                        delete=False,
                        newline="",
                        encoding="utf-8",
                    )
                    writer = csv.DictWriter(tmp, fieldnames=list(page[0].keys()), extrasaction="ignore")
                    writer.writeheader()

                writer.writerows(page)
                total_count += len(page)
                logger.debug("[%s] Streamed %d rows (offset=%d, total=%d)",
                             self.SOURCE_NAME, len(page), offset, total_count)

                api_total = data.get("count", 0)
                if total_count >= api_total or len(page) < page_size:
                    break
                offset += page_size
        finally:
            if tmp is not None:
                tmp.close()

        if total_count == 0:
            return None, 0

        logger.info("[%s] %d total records streamed to %s", self.SOURCE_NAME, total_count, tmp.name)
        return tmp.name, total_count

    def fetch(self, **kwargs) -> Dict[str, Any]:
        max_records = kwargs.get("max_records")
        try:
            tmp_path, count = self._fetch_open_payments_to_csv(max_records)
            if not tmp_path:
                return {"status": "success", "records": [], "record_count": 0, "hash": None, "extracted_files": []}
            return {
                "status": "success",
                "records": count,
                "record_count": count,
                "hash": None,
                "extracted_files": [tmp_path],
            }
        except Exception as e:
            logger.exception("%s fetch failed: %s", self.SOURCE_NAME, e)
            return {"status": "failed", "error": str(e), "records": [], "record_count": 0, "hash": None}
