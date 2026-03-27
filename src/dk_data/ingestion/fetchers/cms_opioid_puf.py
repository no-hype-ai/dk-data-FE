"""CMS Medicare Opioid Prescribing Geographic Variation PUF fetcher stub. File is downloaded by CronJob."""
import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSOpioidPUFFetcher(BaseFetcher):
    SOURCE_NAME = "cms_opioid_puf"
    BASE_URL = "https://data.cms.gov/special-programs-initiatives-opioids-public-use-file/opioid-prescribing-geographic-variation"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """CMS PUF file-based source — download handled externally by CronJob."""
        logger.info("cms_opioid_puf: file-based source; use --file flag with ingestion.main")
        return {"status": "success", "records": [], "hash": None}

    def get_latest_url(self) -> str:
        return self.BASE_URL
