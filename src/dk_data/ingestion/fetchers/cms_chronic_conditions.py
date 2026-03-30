"""CMS Medicare Chronic Conditions prevalence fetcher stub. File is downloaded by CronJob."""
import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSChronicConditionsFetcher(BaseFetcher):
    SOURCE_NAME = "cms_chronic_conditions"
    BASE_URL = "https://data.cms.gov/medicare-chronic-conditions/multiple-chronic-conditions"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """CMS PUF file-based source — download handled externally by CronJob."""
        logger.info("cms_chronic_conditions: file-based source; use --file flag with ingestion.main")
        return {"status": "success", "records": [], "hash": None}

    def get_latest_url(self) -> str:
        return self.BASE_URL
