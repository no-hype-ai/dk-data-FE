"""CMS Geographic Variation Public Use File (GV PUF) Fetcher.

Feature: 019-cms-puf-platform-reconciliation

Fetches CMS Medicare Geographic Variation data which provides state- and
county-level Medicare utilization, spending, and readmission metrics.

Source:
  https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-geographic-comparisons/medicare-geographic-variation-by-national-state-county

CMS migrated from ZIP file downloads to the data.cms.gov API (as of 2026).
Old ZIP URLs (cms.gov/files/zip/*) return 404.

Dataset UUIDs discovered from https://data.cms.gov/data.json:
  National/State/County: 6219697b-8f6c-4164-bed4-cd9317c58ebc
  HRR:                   6d7b229d-5bfb-4666-a2d2-38cea44a112c

The paginated JSON API returns list of dicts with keys like:
  YEAR, BENE_GEO_LVL, BENE_GEO_DESC, BENE_GEO_CD, BENE_AGE_LVL, ...
"""

import hashlib
import logging
from typing import Any, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# data.cms.gov paginated data API base
_DATA_API_BASE = "https://data.cms.gov/data-api/v1/dataset"

# Dataset UUIDs from data.cms.gov/data.json (stable CMS identifiers)
_DATASET_NATIONAL_STATE_COUNTY = "6219697b-8f6c-4164-bed4-cd9317c58ebc"
_DATASET_HRR = "6d7b229d-5bfb-4666-a2d2-38cea44a112c"

# Direct CSV download (full 2014-2023 data, ~large file — use API for seeding)
_CSV_DOWNLOAD_URL = (
    "https://data.cms.gov/sites/default/files/2025-03/"
    "a40ac71d-9f80-4d99-92d2-fd149433d7d8/"
    "2014-2023%20Medicare%20Fee-for-Service%20Geographic%20Variation%20Public%20Use%20File.csv"
)

_PAGE_SIZE = 2000  # Max rows per API call


class CMSGeographicVariationFetcher(BaseFetcher):
    """Fetcher for CMS Medicare Geographic Variation PUF data."""

    SOURCE_NAME = "cms_geographic_variation"
    BASE_URL = f"{_DATA_API_BASE}/{_DATASET_NATIONAL_STATE_COUNTY}/data"

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)

    def get_latest_url(self) -> str:
        return self.BASE_URL

    def fetch(self, **kwargs) -> dict[str, Any]:
        """Fetch CMS Geographic Variation data from the data.cms.gov API.

        Keyword Args:
            max_records: Maximum rows to return (default: all).
            dataset_uuid: Override the dataset UUID (default: national/state/county).

        Returns:
            Fetch result dictionary with status, records, hash.
        """
        max_records: Optional[int] = kwargs.get("max_records")
        dataset_uuid: str = kwargs.get("dataset_uuid", _DATASET_NATIONAL_STATE_COUNTY)

        try:
            records = self._fetch_paginated(dataset_uuid, max_records)
            content_hash = hashlib.md5(str(len(records)).encode()).hexdigest() if records else None
            result: dict[str, Any] = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
                "dataset_uuid": dataset_uuid,
            }
            self.log_fetch_result({**result, "records": len(records)})
            return result

        except Exception as e:
            logger.exception("CMS Geographic Variation fetch failed: %s", e)
            result = {
                "status": "failed",
                "error": str(e),
                "records": [],
                "record_count": 0,
                "hash": None,
            }
            self.log_fetch_result(result)
            return result

    def _fetch_paginated(
        self, dataset_uuid: str, max_records: Optional[int]
    ) -> list[dict[str, Any]]:
        """Fetch all records from the data.cms.gov paginated JSON API."""
        api_url = f"{_DATA_API_BASE}/{dataset_uuid}/data"
        records: list[dict[str, Any]] = []
        offset = 0

        logger.info("Fetching geographic variation via API: %s", api_url)

        while True:
            if max_records is not None and len(records) >= max_records:
                break

            page_size = _PAGE_SIZE
            if max_records is not None:
                page_size = min(_PAGE_SIZE, max_records - len(records))

            params = {"size": page_size, "offset": offset}
            resp = self.session.get(api_url, params=params, timeout=60)
            resp.raise_for_status()

            page: list[dict[str, Any]] = resp.json()
            if not page:
                break

            records.extend(page)
            logger.debug("Fetched %d records (offset=%d)", len(records), offset)

            if len(page) < page_size:
                break  # Last page — stop

            offset += page_size

        logger.info("Fetched %d total records from geographic variation API", len(records))
        return records
