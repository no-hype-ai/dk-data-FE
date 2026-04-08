"""CMS Home Health Agency post-acute care utilization fetcher.

Dataset: Medicare Post-Acute Care Utilization - Home Health Agency
UUID: 43ef03ce-2b60-40a8-958e-146195b5fec7
API: https://data.cms.gov/data-api/v1/dataset/43ef03ce-2b60-40a8-958e-146195b5fec7/data

Column names from this API are uppercase (PRVDR_ID, SRVC_CTGRY, etc.) — the
source loader COLUMN_MAPPING handles the translation.
"""
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher, resolve_cms_latest_year

logger = logging.getLogger(__name__)


class CMSHomeHealthFetcher(BaseFetcher):
    SOURCE_NAME = "cms_home_health"
    # Canonical UUID — fetches most recent available year.
    # Pass years=[2021, 2022, 2023] to backfill multiple years dynamically.
    DATASET_UUID = "43ef03ce-2b60-40a8-958e-146195b5fec7"

    def get_latest_url(self) -> str:
        return f"https://data.cms.gov/data-api/v1/dataset/{self.DATASET_UUID}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        max_records = kwargs.get("max_records")
        years: Optional[List[int]] = kwargs.get("years")
        source_year = int(kwargs.get("fiscal_year") or kwargs.get("source_year") or resolve_cms_latest_year(self.DATASET_UUID))
        try:
            from ..sources.cms_home_health import load_cms_home_health
            from ..utils.checkpoint import clear_checkpoint
            if years:
                total_fetched, total_inserted = self._stream_cms_api_multi_year_to_db(
                    self.DATASET_UUID, load_cms_home_health, years=years, max_records_per_year=max_records
                )
            else:
                total_fetched, total_inserted = self._stream_cms_api_to_db(
                    self.DATASET_UUID, load_cms_home_health, source_year=source_year, max_records=max_records
                )
            clear_checkpoint(self.SOURCE_NAME)
            return {"status": "success", "records": [], "record_count": total_inserted, "hash": None}
        except Exception as e:
            logger.exception("%s fetch failed: %s", self.SOURCE_NAME, e)
            return {"status": "failed", "error": str(e), "records": [], "record_count": 0, "hash": None}
