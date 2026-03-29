"""CMS Medicare Monthly Enrollment PUF fetcher."""
import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSEnrollmentPUFFetcher(BaseFetcher):
    SOURCE_NAME = "cms_enrollment_puf"
    DATASET_UUID = "d7fabe1e-d19b-4333-9eff-e80e0643f2fd"

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
