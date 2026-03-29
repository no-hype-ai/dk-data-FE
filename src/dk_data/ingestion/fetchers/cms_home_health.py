"""CMS Home Health Agency post-acute care utilization fetcher.

Dataset: Medicare Post-Acute Care Utilization - Home Health Agency
UUID: 43ef03ce-2b60-40a8-958e-146195b5fec7
API: https://data.cms.gov/data-api/v1/dataset/43ef03ce-2b60-40a8-958e-146195b5fec7/data

Column names from this API are uppercase (PRVDR_ID, SRVC_CTGRY, etc.) — the
source loader COLUMN_MAPPING handles the translation.
"""
import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSHomeHealthFetcher(BaseFetcher):
    SOURCE_NAME = "cms_home_health"
    DATASET_UUID = "43ef03ce-2b60-40a8-958e-146195b5fec7"

    def get_latest_url(self) -> str:
        return f"https://data.cms.gov/data-api/v1/dataset/{self.DATASET_UUID}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        max_records = kwargs.get("max_records")
        try:
            records = self._fetch_cms_api(self.DATASET_UUID, max_records)
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
