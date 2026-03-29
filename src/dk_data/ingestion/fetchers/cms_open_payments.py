"""CMS Open Payments (Sunshine Act) fetcher.

Uses the openpaymentsdata.cms.gov DKAN API (separate portal from data.cms.gov).
Most recent dataset: 2024 General Payment Data
UUID: e6b17c6a-2534-4207-a4a1-6746a14911ff
API: https://openpaymentsdata.cms.gov/api/1/datastore/query/{uuid}/0

The DKAN datastore query endpoint supports offset/limit pagination.
Response shape: {"results": [...], "count": N, "schema": {...}}
"""
import logging
from typing import Any, Dict, List

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

    def _fetch_open_payments(self, max_records: int | None = None) -> List[Dict[str, Any]]:
        """Paginate through the DKAN datastore query endpoint."""
        api_url = f"{_OPEN_PAYMENTS_API}/{self.DATASET_UUID}/0"
        records: List[Dict[str, Any]] = []
        offset = 0

        logger.info("[%s] Fetching from openpaymentsdata.cms.gov: %s", self.SOURCE_NAME, api_url)

        while True:
            remaining = None if max_records is None else max_records - len(records)
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

            page = data.get("results", [])
            if not page:
                break
            records.extend(page)
            logger.debug("[%s] Fetched %d records (offset=%d)", self.SOURCE_NAME, len(records), offset)

            total = data.get("count", 0)
            if len(records) >= total:
                break
            if len(page) < page_size:
                break
            offset += page_size

        logger.info("[%s] %d total records fetched", self.SOURCE_NAME, len(records))
        return records

    def fetch(self, **kwargs) -> Dict[str, Any]:
        max_records = kwargs.get("max_records")
        try:
            records = self._fetch_open_payments(max_records)
            if not records:
                return {"status": "success", "records": [], "record_count": 0, "hash": None, "extracted_files": []}
            tmp_path = self._cms_records_to_csv(records)
            return {
                "status": "success",
                "records": len(records),
                "record_count": len(records),
                "hash": None,
                "extracted_files": [tmp_path],
            }
        except Exception as e:
            logger.exception("%s fetch failed: %s", self.SOURCE_NAME, e)
            return {"status": "failed", "error": str(e), "records": [], "record_count": 0, "hash": None}
