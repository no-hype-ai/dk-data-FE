"""CMS Medicare Referring Providers PUF fetcher."""
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher, resolve_cms_latest_year

logger = logging.getLogger(__name__)


class CMSReferringProvidersFetcher(BaseFetcher):
    SOURCE_NAME = "cms_referring_providers"
    DATASET_UUID = "c99b5865-1119-4436-bb80-c5af2773ea1f"

    def get_latest_url(self) -> str:
        return f"https://data.cms.gov/data-api/v1/dataset/{self.DATASET_UUID}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        max_records = kwargs.get("max_records")
        years: Optional[List[int]] = kwargs.get("years")
        source_year = int(kwargs.get("fiscal_year") or kwargs.get("source_year") or resolve_cms_latest_year(self.DATASET_UUID))
        try:
            from ..sources.cms_referring_providers import load_cms_referring_providers
            from ..utils.checkpoint import clear_checkpoint
            if years:
                total_fetched, total_inserted = self._stream_cms_api_multi_year_to_db(
                    self.DATASET_UUID, load_cms_referring_providers, years=years, max_records_per_year=max_records
                )
            else:
                total_fetched, total_inserted = self._stream_cms_api_to_db(
                    self.DATASET_UUID, load_cms_referring_providers, source_year=source_year, max_records=max_records
                )
            clear_checkpoint(self.SOURCE_NAME)
            return {"status": "success", "records": [], "record_count": total_inserted, "hash": None}
        except Exception as e:
            logger.exception("%s fetch failed: %s", self.SOURCE_NAME, e)
            return {"status": "failed", "error": str(e), "records": [], "record_count": 0, "hash": None}
