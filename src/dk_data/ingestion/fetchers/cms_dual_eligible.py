"""CMS Medicare-Medicaid Dual Eligible beneficiaries fetcher stub. File is downloaded by CronJob."""
import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSDualEligibleFetcher(BaseFetcher):
    SOURCE_NAME = "cms_dual_eligible"
    BASE_URL = "https://data.cms.gov/medicare-medicaid-coordination/medicare-and-medicaid-enrollment/medicare-medicaid-dual-enrollment"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """CMS PUF file-based source — download handled externally by CronJob."""
        logger.info("cms_dual_eligible: file-based source; use --file flag with ingestion.main")
        return {"status": "success", "records": [], "hash": None}

    def get_latest_url(self) -> str:
        return self.BASE_URL
