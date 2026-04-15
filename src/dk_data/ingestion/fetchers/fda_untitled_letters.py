"""FDA Untitled Letters fetcher — scrapes FDA untitled letter index.

Source: https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/untitled-letters
Target table: mol_raw.fda_untitled_letters
Feature: 006-claims-engine-data-gaps (T073)
"""

import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_FDA_UNTITLED_LETTERS_URL = (
    "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/"
    "compliance-actions-and-activities/untitled-letters"
)

FETCHER_CONFIG = {
    "source_name": "fda_untitled_letters",
    "target_table": "mol_raw.fda_untitled_letters",
    "source_url": _FDA_UNTITLED_LETTERS_URL,
    "schedule": "weekly",
    "notes": (
        "FDA publishes untitled letters (less severe than warning letters) "
        "as HTML pages. Fetcher should paginate the search index, download "
        "individual letters, extract full text and drug mentions."
    ),
}


class FDAUntitledLettersFetcher(BaseFetcher):
    """Fetcher for FDA Untitled Letters."""

    SOURCE_NAME = "fda_untitled_letters"
    BASE_URL = "https://www.fda.gov"

    def get_latest_url(self) -> str:
        return _FDA_UNTITLED_LETTERS_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch FDA untitled letters.

        TODO: Implement pagination over FDA untitled-letter search index,
        download each letter page, parse HTML for company/drug metadata,
        extract drug mentions via NLP/regex, and upsert into
        mol_raw.fda_untitled_letters.

        Returns:
            Fetch result dictionary with status, records, count, hash.
        """
        raise NotImplementedError(
            "FDAUntitledLettersFetcher.fetch() is a stub — "
            "implementation pending data-source onboarding."
        )
