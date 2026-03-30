"""CMS Medicare Utilization by Service Category PUF fetcher."""
import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSUtilizationPUFFetcher(BaseFetcher):
    SOURCE_NAME = "cms_utilization_puf"
    # Medicare Geographic Variation by National, State & County — utilization & spending rates.
    # (UUID 8889d81e was "by Provider" — wrong dataset entirely.)
    DATASET_UUID = "6219697b-8f6c-4164-bed4-cd9317c58ebc"

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
