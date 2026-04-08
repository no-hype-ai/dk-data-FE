"""CMS Medicare Mental Health Services PUF fetcher.

Mental health services fetched from the Medicare Physician & Other
Practitioners - by Provider and Service PUF, filtered by mental health
provider types.
"""
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher, resolve_cms_latest_year

logger = logging.getLogger(__name__)

_MENTAL_HEALTH_PROVIDER_TYPES = ['Psychiatry', 'Clinical Psychologist', 'Clinical Social Worker', 'Mental Health Counselor', 'Licensed Clinical Social Worker', 'Addiction Medicine', 'Neurology']

class CMSMentalHealthPUFFetcher(BaseFetcher):
    SOURCE_NAME = "cms_mental_health_puf"
    # Medicare Physician & Other Practitioners - by Provider and Service.
    # Canonical UUID — pass years=[2021, 2022, 2023] to backfill multiple years dynamically.
    DATASET_UUID = "92396110-2aed-4d63-a6a2-5d6207d46a29"

    def get_latest_url(self) -> str:
        return f"https://data.cms.gov/data-api/v1/dataset/{self.DATASET_UUID}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        max_records = kwargs.get("max_records")
        years: Optional[List[int]] = kwargs.get("years")
        source_year = int(kwargs.get("fiscal_year") or kwargs.get("source_year") or resolve_cms_latest_year(self.DATASET_UUID))
        try:
            from ..sources.cms_mental_health_puf import load_cms_mental_health_puf
            from ..utils.checkpoint import clear_checkpoint
            total_fetched = 0
            total_inserted = 0
            for provider_type in _MENTAL_HEALTH_PROVIDER_TYPES:
                filter_params = {"filter[Rndrng_Prvdr_Type][value]": provider_type}
                if years:
                    fetched, inserted = self._stream_cms_api_multi_year_to_db(
                        self.DATASET_UUID, load_cms_mental_health_puf, years=years,
                        max_records_per_year=max_records, filter_params=filter_params,
                    )
                else:
                    fetched, inserted = self._stream_cms_api_to_db(
                        self.DATASET_UUID, load_cms_mental_health_puf, source_year=source_year,
                        max_records=max_records, filter_params=filter_params,
                    )
                total_fetched += fetched
                total_inserted += inserted
            clear_checkpoint(self.SOURCE_NAME)
            return {"status": "success", "records": [], "record_count": total_inserted, "hash": None}
        except Exception as e:
            logger.exception("%s fetch failed: %s", self.SOURCE_NAME, e)
            return {"status": "failed", "error": str(e), "records": [], "record_count": 0, "hash": None}
