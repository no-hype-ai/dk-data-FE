"""CMS Part D Prescriber PUF fetcher stub.

This is a file-based CMS source — the actual CSV is downloaded by a CronJob
(or manually via the CMS CKAN API). The fetcher stub satisfies the ingestion
framework's fetcher contract without doing a live download.

Data source:
    CMS Medicare Part D Prescribers — by Provider and Drug
    https://data.cms.gov/provider-summary-by-type-of-service/medicare-part-d-prescribers/medicare-part-d-prescribers-by-provider-and-drug

Usage:
    python -m dk_data.ingestion.main cms_part_d_prescriber --file <path> --year 2023
"""

import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSPartDPrescriberFetcher(BaseFetcher):
    SOURCE_NAME = "cms_part_d_prescriber"
    BASE_URL = (
        "https://data.cms.gov/provider-summary-by-type-of-service"
        "/medicare-part-d-prescribers/medicare-part-d-prescribers-by-provider-and-drug"
    )

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """CMS PUF file-based source — download handled externally.

        Use --file <path> when calling ingestion.main directly.
        The CronJob downloads via cms_downloader before invoking this loader.
        """
        logger.info(
            "cms_part_d_prescriber: file-based source; use --file flag with ingestion.main"
        )
        return {"status": "success", "records": [], "hash": None}

    def get_latest_url(self) -> str:
        return self.BASE_URL
