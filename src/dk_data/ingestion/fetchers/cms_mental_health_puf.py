"""CMS Medicare Mental Health Services PUF fetcher.

The dedicated CMS Mental Health Services PUF was retired as a standalone dataset.
Mental health services are now available through the Medicare Physician & Other
Practitioners - by Provider and Service PUF, filtered by mental health provider types.

Dataset UUID: 92396110-2aed-4d63-a6a2-5d6207d46a29
(Same source as cms_physician_puf, cms_imaging_puf, cms_telehealth_puf)

Provider types for mental health filtering:
  Psychiatry, Clinical Psychologist, Clinical Social Worker,
  Mental Health Counselor, Licensed Clinical Social Worker,
  Addiction Medicine, Neurology
"""
import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Provider types in the Physician PUF that correspond to mental health services.
_MENTAL_HEALTH_PROVIDER_TYPES = [
    "Psychiatry",
    "Clinical Psychologist",
    "Clinical Social Worker",
    "Mental Health Counselor",
    "Licensed Clinical Social Worker",
    "Addiction Medicine",
    "Neurology",
]


class CMSMentalHealthPUFFetcher(BaseFetcher):
    SOURCE_NAME = "cms_mental_health_puf"
    # Medicare Physician & Other Practitioners - by Provider and Service
    DATASET_UUID = "92396110-2aed-4d63-a6a2-5d6207d46a29"

    def get_latest_url(self) -> str:
        return f"https://data.cms.gov/data-api/v1/dataset/{self.DATASET_UUID}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        max_records = kwargs.get("max_records")
        all_records = []
        try:
            for provider_type in _MENTAL_HEALTH_PROVIDER_TYPES:
                filter_params = {"filter[Rndrng_Prvdr_Type][value]": provider_type}
                records = self._fetch_cms_api(
                    self.DATASET_UUID,
                    max_records=max_records,
                    filter_params=filter_params,
                )
                logger.info("[%s] %d records for provider_type=%s", self.SOURCE_NAME, len(records), provider_type)
                all_records.extend(records)
                if max_records and len(all_records) >= max_records:
                    all_records = all_records[:max_records]
                    break

            if not all_records:
                return {"status": "success", "records": [], "record_count": 0, "hash": None, "extracted_files": []}
            tmp_path = self._cms_records_to_csv(all_records)
            return {
                "status": "success",
                "records": len(all_records),
                "record_count": len(all_records),
                "hash": None,
                "extracted_files": [tmp_path],
            }
        except Exception as e:
            logger.exception("%s fetch failed: %s", self.SOURCE_NAME, e)
            return {"status": "failed", "error": str(e), "records": [], "record_count": 0, "hash": None}
