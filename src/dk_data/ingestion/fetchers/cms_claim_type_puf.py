"""CMS Medicare Claims by Type and Service Category PUF fetcher."""
import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSClaimTypePUFFetcher(BaseFetcher):
    SOURCE_NAME = "cms_claim_type_puf"
    DATASET_UUID = "164fc736-4179-4100-9f79-592b69e41975"

    def get_latest_url(self) -> str:
        return f"https://data.cms.gov/data-api/v1/dataset/{self.DATASET_UUID}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        max_records = kwargs.get("max_records")
        source_year = int(kwargs.get("fiscal_year") or kwargs.get("source_year") or 2023)
        try:
            from ..sources.cms_claim_type_puf import load_cms_claim_type_puf
            from ..utils.checkpoint import clear_checkpoint
            total_fetched, total_inserted = self._stream_cms_api_to_db(
                self.DATASET_UUID, load_cms_claim_type_puf, source_year=source_year, max_records=max_records
            )
            clear_checkpoint(self.SOURCE_NAME)
            return {"status": "success", "records": [], "record_count": total_inserted, "hash": None}
        except Exception as e:
            logger.exception("%s fetch failed: %s", self.SOURCE_NAME, e)
            return {"status": "failed", "error": str(e), "records": [], "record_count": 0, "hash": None}
