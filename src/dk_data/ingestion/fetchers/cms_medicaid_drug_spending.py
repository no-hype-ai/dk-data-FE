"""CMS Medicaid Drug Spending fetcher."""
import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSMedicaidDrugSpendingFetcher(BaseFetcher):
    SOURCE_NAME = "cms_medicaid_drug_spending"
    DATASET_UUID = "be64fce3-e835-4589-b46b-024198e524a6"

    def get_latest_url(self) -> str:
        return f"https://data.cms.gov/data-api/v1/dataset/{self.DATASET_UUID}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        max_records = kwargs.get("max_records")
        try:
            tmp_path, count = self._fetch_cms_api_to_csv(self.DATASET_UUID, max_records)
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
