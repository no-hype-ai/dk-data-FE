"""CMS Medicare Geographic Variation Public Use File fetcher stub. File is downloaded by CronJob."""
import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSGeographicVariationFetcher(BaseFetcher):
    SOURCE_NAME = "cms_geographic_variation"
    BASE_URL = "https://data.cms.gov/summary-statistics-information-and-methods/research-statistics-data-and-systems/geographic-variation-public-use-files"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """CMS PUF file-based source — download handled externally by CronJob."""
        logger.info("cms_geographic_variation: file-based source; use --file flag with ingestion.main")
        return {"status": "success", "records": [], "hash": None}

    def get_latest_url(self) -> str:
        return self.BASE_URL
