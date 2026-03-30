"""CMS Medicare Lab Services PUF fetcher.

No standalone lab-services provider utilization dataset exists in the CMS catalog.
UUID 0e57f57d-0acc-4c9c-8f8c-973e3f4a3c4b is the Clinical Lab Fee Schedule (CLFS) —
a pricing file (hcpcs_cd, PRICE_AMT, VOL_TXT), not provider-level utilization.

Provider-level lab utilization is fetched from the Medicare Physician & Other
Practitioners - by Provider and Service PUF (same source as cms_physician_puf),
filtered by lab-related provider types: Clinical Laboratory, Pathology.

Dataset UUID: 92396110-2aed-4d63-a6a2-5d6207d46a29
Confirmed filter values (GET /data-api/v1/.../data?filter[Rndrng_Prvdr_Type][value]=..., 2026-03-29):
  Clinical Laboratory — returns provider-level NPI × HCPCS records ✓
  Pathology          — returns provider-level NPI × HCPCS records ✓
"""
import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_LAB_PROVIDER_TYPES = [
    "Clinical Laboratory",
    "Pathology",
]


class CMSLabServicesFetcher(BaseFetcher):
    SOURCE_NAME = "cms_lab_services"
    # Medicare Physician & Other Practitioners - by Provider and Service
    # (same source as cms_physician_puf / cms_imaging_puf / cms_mental_health_puf)
    DATASET_UUID = "92396110-2aed-4d63-a6a2-5d6207d46a29"

    def get_latest_url(self) -> str:
        return f"https://data.cms.gov/data-api/v1/dataset/{self.DATASET_UUID}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        max_records = kwargs.get("max_records")
        all_records = []
        try:
            for provider_type in _LAB_PROVIDER_TYPES:
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
