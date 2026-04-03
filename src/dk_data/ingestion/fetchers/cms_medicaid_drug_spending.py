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
        source_year = int(kwargs.get("fiscal_year") or kwargs.get("source_year") or 2023)
        try:
            from ..sources.cms_medicaid_drug_spending import load_cms_medicaid_drug_spending
            from ..utils.checkpoint import clear_checkpoint
            total_fetched, total_inserted = self._stream_cms_api_to_db(
                self.DATASET_UUID, load_cms_medicaid_drug_spending, source_year=source_year, max_records=max_records
            )
            clear_checkpoint(self.SOURCE_NAME)
            return {"status": "success", "records": [], "record_count": total_inserted, "hash": None}
        except Exception as e:
            logger.exception("%s fetch failed: %s", self.SOURCE_NAME, e)
            return {"status": "failed", "error": str(e), "records": [], "record_count": 0, "hash": None}
