"""CMS Medicare Telehealth Utilization PUF fetcher."""
import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSTelehealthPUFFetcher(BaseFetcher):
    SOURCE_NAME = "cms_telehealth_puf"
    # Medicare Physician & Other Practitioners - by Provider and Service.
    # CMS does not publish a separate telehealth-only provider PUF; the
    # Place_Of_Srvc column in this dataset encodes telehealth ('02') vs
    # in-person services — mapped to th_srvc_ind in the source loader.
    DATASET_UUID = "92396110-2aed-4d63-a6a2-5d6207d46a29"

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
