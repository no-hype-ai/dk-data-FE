"""CMS Medicare Advantage enrollment fetcher stub. File is downloaded by CronJob."""
import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSMedicareAdvantageFetcher(BaseFetcher):
    SOURCE_NAME = "cms_medicare_advantage"
    BASE_URL = "https://data.cms.gov/medicare-enrollment/enrollment-performance-indicators/state-county-penetration"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """CMS PUF file-based source — download handled externally by CronJob."""
        logger.info("cms_medicare_advantage: file-based source; use --file flag with ingestion.main")
        return {"status": "success", "records": [], "hash": None}

    def get_latest_url(self) -> str:
        return self.BASE_URL
