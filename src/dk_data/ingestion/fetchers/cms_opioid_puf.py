"""CMS Medicare Part D Opioid Prescriber Summary File fetcher.

Corrected dataset: "Medicare Part D Prescribers - by Provider and Drug"
UUID: 9552739e-3d05-4c1b-8eff-ecabf391e2e5

Previous UUID (94d00f36-...) was wrong — it pointed to geographic-level
aggregates, NOT the prescriber+drug-level data needed for NPI-level analysis.
"""
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSOpioidPUFFetcher(BaseFetcher):
    SOURCE_NAME = "cms_opioid_puf"
    # Medicare Part D Prescribers - by Provider and Drug.
    # Same source as cms_part_d_prescriber — pass years=[2021, 2022, 2023] to backfill.
    DATASET_UUID = "9552739e-3d05-4c1b-8eff-ecabf391e2e5"

    def get_latest_url(self) -> str:
        return f"https://data.cms.gov/data-api/v1/dataset/{self.DATASET_UUID}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        max_records = kwargs.get("max_records")
        years: Optional[List[int]] = kwargs.get("years")
        try:
            if years:
                csv_paths = self._fetch_cms_api_multi_year(
                    self.DATASET_UUID, years, max_records_per_year=max_records
                )
                if not csv_paths:
                    return {"status": "success", "records": 0, "record_count": 0, "hash": None, "extracted_files": []}
                return {
                    "status": "success",
                    "records": len(csv_paths),
                    "record_count": len(csv_paths),
                    "hash": None,
                    "extracted_files": csv_paths,
                }
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
