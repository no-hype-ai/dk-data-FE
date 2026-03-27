"""CMS Medicare Telehealth Utilization PUF fetcher stub. File is downloaded by CronJob."""
import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSTelehealthPUFFetcher(BaseFetcher):
    SOURCE_NAME = "cms_telehealth_puf"
    BASE_URL = "https://data.cms.gov/provider-summary-by-type-of-service/telehealth-utilization"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """CMS PUF file-based source — download handled externally by CronJob."""
        logger.info("cms_telehealth_puf: file-based source; use --file flag with ingestion.main")
        return {"status": "success", "records": [], "hash": None}

    def get_latest_url(self) -> str:
        return self.BASE_URL
