"""CMS Medicare Lab Services PUF fetcher.

Provider-level lab utilization fetched from the Medicare Physician & Other
Practitioners - by Provider and Service PUF, filtered by lab-related provider types.
"""
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_LAB_PROVIDER_TYPES = ['Clinical Laboratory', 'Pathology']

class CMSLabServicesFetcher(BaseFetcher):
    SOURCE_NAME = "cms_lab_services"
    # Medicare Physician & Other Practitioners - by Provider and Service.
    # Canonical UUID — pass years=[2021, 2022, 2023] to backfill multiple years dynamically.
    DATASET_UUID = "92396110-2aed-4d63-a6a2-5d6207d46a29"

    def get_latest_url(self) -> str:
        return f"https://data.cms.gov/data-api/v1/dataset/{self.DATASET_UUID}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        max_records = kwargs.get("max_records")
        years: Optional[List[int]] = kwargs.get("years")
        
        try:
            if years:
                all_paths: List[str] = []
                for provider_type in _LAB_PROVIDER_TYPES:
                    filter_params = {"filter[Rndrng_Prvdr_Type][value]": provider_type}
                    paths = self._fetch_cms_api_multi_year(
                        self.DATASET_UUID, years,
                        max_records_per_year=max_records,
                        filter_params=filter_params,
                    )
                    all_paths.extend(paths)
                if not all_paths:
                    return {"status": "success", "records": 0, "record_count": 0, "hash": None, "extracted_files": []}
                return {
                    "status": "success",
                    "records": len(all_paths),
                    "record_count": len(all_paths),
                    "hash": None,
                    "extracted_files": all_paths,
                }
            csv_paths = []
            total_count = 0
            for provider_type in _LAB_PROVIDER_TYPES:
                filter_params = {"filter[Rndrng_Prvdr_Type][value]": provider_type}
                path, count = self._fetch_cms_api_to_csv(
                    self.DATASET_UUID,
                    max_records=max_records,
                    filter_params=filter_params,
                )
                if path:
                    logger.info("[%s] %d records for provider_type=%s", self.SOURCE_NAME, count, provider_type)
                    csv_paths.append(path)
                    total_count += count
                if max_records and total_count >= max_records:
                    break

            if not csv_paths:
                return {"status": "success", "records": [], "record_count": 0, "hash": None, "extracted_files": []}
            return {
                "status": "success",
                "records": total_count,
                "record_count": total_count,
                "hash": None,
                "extracted_files": csv_paths,
            }
        except Exception as e:
            logger.exception("%s fetch failed: %s", self.SOURCE_NAME, e)
            return {"status": "failed", "error": str(e), "records": [], "record_count": 0, "hash": None}
