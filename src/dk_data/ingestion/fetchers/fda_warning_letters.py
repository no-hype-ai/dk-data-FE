"""FDA Warning Letters fetcher — scrapes FDA warning letter index.

Source: https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters
Target table: mol_raw.fda_warning_letters
Feature: 006-claims-engine-data-gaps (T073)
"""

import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# FDA Warning Letters landing page & search API
_FDA_WARNING_LETTERS_URL = (
    "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/"
    "compliance-actions-and-activities/warning-letters"
)

FETCHER_CONFIG = {
    "source_name": "fda_warning_letters",
    "target_table": "mol_raw.fda_warning_letters",
    "source_url": _FDA_WARNING_LETTERS_URL,
    "schedule": "weekly",
    "notes": (
        "FDA publishes warning letters as HTML pages with a searchable index. "
        "Fetcher should paginate the search API, download individual letter pages, "
        "extract full text and drug mentions via NLP/regex."
    ),
}


class FDAWarningLettersFetcher(BaseFetcher):
    """Fetcher for FDA Warning Letters."""

    SOURCE_NAME = "fda_warning_letters"
    BASE_URL = "https://www.fda.gov"

    def get_latest_url(self) -> str:
        return _FDA_WARNING_LETTERS_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch FDA warning letters.

        TODO: Implement pagination over FDA warning-letter search index,
        download each letter page, parse HTML for company/drug metadata,
        extract drug mentions via NLP/regex, and upsert into
        mol_raw.fda_warning_letters.

        Returns:
            Fetch result dictionary with status, records, count, hash.
        """
        raise NotImplementedError(
            "FDAWarningLettersFetcher.fetch() is a stub — "
            "implementation pending data-source onboarding."
        )
