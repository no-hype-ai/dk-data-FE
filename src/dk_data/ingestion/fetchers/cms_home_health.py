"""CMS Home Health Agency Compare fetcher stub. File is downloaded by CronJob."""
import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSHomeHealthFetcher(BaseFetcher):
    SOURCE_NAME = "cms_home_health"
    BASE_URL = "https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/home-health-agency-compare"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """CMS PUF file-based source — download handled externally by CronJob."""
        logger.info("cms_home_health: file-based source; use --file flag with ingestion.main")
        return {"status": "success", "records": [], "hash": None}

    def get_latest_url(self) -> str:
        return self.BASE_URL
