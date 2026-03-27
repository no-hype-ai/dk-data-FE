"""CMS Medicare Lab Services PUF fetcher stub. File is downloaded by CronJob."""
import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSLabServicesFetcher(BaseFetcher):
    SOURCE_NAME = "cms_lab_services"
    BASE_URL = "https://data.cms.gov/provider-summary-by-type-of-service/lab-services"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """CMS PUF file-based source — download handled externally by CronJob."""
        logger.info("cms_lab_services: file-based source; use --file flag with ingestion.main")
        return {"status": "success", "records": [], "hash": None}

    def get_latest_url(self) -> str:
        return self.BASE_URL
