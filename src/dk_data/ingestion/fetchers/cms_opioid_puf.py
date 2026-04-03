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
        source_year = int(kwargs.get("fiscal_year") or kwargs.get("source_year") or 2023)
        try:
            from ..sources.cms_opioid_puf import load_cms_opioid_puf
            from ..utils.checkpoint import clear_checkpoint
            if years:
                total_fetched, total_inserted = self._stream_cms_api_multi_year_to_db(
                    self.DATASET_UUID, load_cms_opioid_puf, years=years, max_records_per_year=max_records
                )
            else:
                total_fetched, total_inserted = self._stream_cms_api_to_db(
                    self.DATASET_UUID, load_cms_opioid_puf, source_year=source_year, max_records=max_records
                )
            clear_checkpoint(self.SOURCE_NAME)
            return {"status": "success", "records": [], "record_count": total_inserted, "hash": None}
        except Exception as e:
            logger.exception("%s fetch failed: %s", self.SOURCE_NAME, e)
            return {"status": "failed", "error": str(e), "records": [], "record_count": 0, "hash": None}
