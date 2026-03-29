"""CMS Part D Prescriber PUF fetcher.

Data source:
    CMS Medicare Part D Prescribers — by Provider and Drug
    https://data.cms.gov/provider-summary-by-type-of-service/medicare-part-d-prescribers/medicare-part-d-prescribers-by-provider-and-drug
"""

import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSPartDPrescriberFetcher(BaseFetcher):
    SOURCE_NAME = "cms_part_d_prescriber"
    DATASET_UUID = "9552739e-3d05-4c1b-8eff-ecabf391e2e5"

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
