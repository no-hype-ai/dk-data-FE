"""CMS Medicare Referring Providers PUF fetcher stub. File is downloaded by CronJob."""
import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSReferringProvidersFetcher(BaseFetcher):
    SOURCE_NAME = "cms_referring_providers"
    BASE_URL = "https://data.cms.gov/provider-summary-by-type-of-service/referring-ordering-billing"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """CMS PUF file-based source — download handled externally by CronJob."""
        logger.info("cms_referring_providers: file-based source; use --file flag with ingestion.main")
        return {"status": "success", "records": [], "hash": None}

    def get_latest_url(self) -> str:
        return self.BASE_URL
