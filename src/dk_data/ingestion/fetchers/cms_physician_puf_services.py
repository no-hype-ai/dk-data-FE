"""CMS Medicare Physician PUF by Provider and Service fetcher stub. File is downloaded by CronJob."""
import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSPhysicianPUFServicesFetcher(BaseFetcher):
    SOURCE_NAME = "cms_physician_puf_services"
    BASE_URL = (
        "https://data.cms.gov/provider-summary-by-type-of-service"
        "/medicare-physician-other-practitioners/medicare-physician-other-practitioners-by-provider-and-service"
    )

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """CMS PUF file-based source — download handled externally by CronJob."""
        logger.info(
            "cms_physician_puf_services: file-based source; use --file flag with ingestion.main"
        )
        return {"status": "success", "records": [], "hash": None}

    def get_latest_url(self) -> str:
        return self.BASE_URL
