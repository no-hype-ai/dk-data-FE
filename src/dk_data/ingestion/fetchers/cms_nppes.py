"""CMS NPPES NPI registry fetcher stub. File is downloaded by CronJob."""
import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSNPPESFetcher(BaseFetcher):
    SOURCE_NAME = "cms_nppes"
    BASE_URL = "https://download.cms.gov/nppes/NPI_Files.html"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """CMS PUF file-based source — download handled externally by CronJob."""
        logger.info("cms_nppes: file-based source; use --file flag with ingestion.main")
        return {"status": "success", "records": [], "hash": None}

    def get_latest_url(self) -> str:
        return self.BASE_URL
