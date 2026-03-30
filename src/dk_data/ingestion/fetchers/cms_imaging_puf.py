"""CMS Medicare Imaging Services PUF fetcher.

No standalone imaging dataset exists in the CMS data-api catalog. Imaging
services are fetched from the Medicare Physician & Other Practitioners - by
Provider and Service PUF (same source as cms_physician_puf / cms_telehealth_puf),
filtered server-side to provider types commonly associated with imaging
(Radiology, Diagnostic Radiology, Interventional Radiology, Nuclear Medicine,
Radiation Oncology, Diagnostic Imaging).

Dataset UUID: 92396110-2aed-4d63-a6a2-5d6207d46a29
"""
import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Provider types in the Physician PUF that correspond to imaging services.
# The CMS API filter supports exact match only; we iterate over each type.
_IMAGING_PROVIDER_TYPES = [
    "Diagnostic Radiology",
    "Interventional Radiology",
    "Diagnostic Imaging",
    "Nuclear Medicine",
    "Radiation Oncology",
    "Radiology",
]


class CMSImagingPUFFetcher(BaseFetcher):
    SOURCE_NAME = "cms_imaging_puf"
    # Medicare Physician & Other Practitioners - by Provider and Service
    DATASET_UUID = "92396110-2aed-4d63-a6a2-5d6207d46a29"

    def get_latest_url(self) -> str:
        return f"https://data.cms.gov/data-api/v1/dataset/{self.DATASET_UUID}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        max_records = kwargs.get("max_records")
        all_records = []
        try:
            for provider_type in _IMAGING_PROVIDER_TYPES:
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
