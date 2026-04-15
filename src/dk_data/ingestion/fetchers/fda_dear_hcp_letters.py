"""FDA Dear Healthcare Professional (Dear HCP) Letters fetcher.

Source: https://www.fda.gov/drugs/drug-safety-and-availability/drug-safety-communications
Target table: mol_raw.fda_dear_hcp_letters
Feature: 006-claims-engine-data-gaps (T073)
"""

import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_FDA_DEAR_HCP_URL = (
    "https://www.fda.gov/drugs/drug-safety-and-availability/"
    "drug-safety-communications"
)

FETCHER_CONFIG = {
    "source_name": "fda_dear_hcp_letters",
    "target_table": "mol_raw.fda_dear_hcp_letters",
    "source_url": _FDA_DEAR_HCP_URL,
    "schedule": "weekly",
    "notes": (
        "Dear Healthcare Professional letters are safety communications "
        "from drug manufacturers, often mandated by FDA. They appear on "
        "FDA's Drug Safety Communications page and in MedWatch. Fetcher "
        "should paginate the listing, download each letter, extract drug "
        "name and mentions."
    ),
}


class FDADearHCPLettersFetcher(BaseFetcher):
    """Fetcher for FDA Dear Healthcare Professional Letters."""

    SOURCE_NAME = "fda_dear_hcp_letters"
    BASE_URL = "https://www.fda.gov"

    def get_latest_url(self) -> str:
        return _FDA_DEAR_HCP_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch FDA Dear HCP letters.

        TODO: Implement scraping of FDA Drug Safety Communications page,
        download individual letter pages, extract drug name, company,
        subject, full text, and drug mentions. Upsert into
        mol_raw.fda_dear_hcp_letters.

        Returns:
            Fetch result dictionary with status, records, count, hash.
        """
        raise NotImplementedError(
            "FDADearHCPLettersFetcher.fetch() is a stub — "
            "implementation pending data-source onboarding."
        )
