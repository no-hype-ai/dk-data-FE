"""FDA Complete Response Letters (CRLs) fetcher.

Source: https://www.fda.gov/drugs/new-drugs-fda-cders-new-molecular-entities-and-new-therapeutic-biological-products/complete-response-letters
Note: CRLs are not publicly published by FDA, but summaries are often
disclosed via company press releases and tracked by third-party databases.
Target table: mol_raw.fda_crls
Feature: 006-claims-engine-data-gaps (T073)
"""

import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_FDA_CRLS_URL = (
    "https://www.fda.gov/drugs/new-drugs-fda-cders-new-molecular-entities-"
    "and-new-therapeutic-biological-products/complete-response-letters"
)

FETCHER_CONFIG = {
    "source_name": "fda_crls",
    "target_table": "mol_raw.fda_crls",
    "source_url": _FDA_CRLS_URL,
    "schedule": "weekly",
    "notes": (
        "FDA issues Complete Response Letters when it cannot approve an "
        "NDA/BLA in its current form. CRLs themselves are confidential, "
        "but companies typically disclose receipt and reasons. Fetcher "
        "should aggregate CRL disclosures from FDA press releases and "
        "company filings, extracting drug name, application number, "
        "and reason for the CRL."
    ),
}


class FDACRLsFetcher(BaseFetcher):
    """Fetcher for FDA Complete Response Letters."""

    SOURCE_NAME = "fda_crls"
    BASE_URL = "https://www.fda.gov"

    def get_latest_url(self) -> str:
        return _FDA_CRLS_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch FDA Complete Response Letter records.

        TODO: Implement aggregation of CRL disclosures from FDA press
        releases and company filings. Extract drug name, application
        number, CRL date, reason, and full text. Upsert into
        mol_raw.fda_crls.

        Returns:
            Fetch result dictionary with status, records, count, hash.
        """
        raise NotImplementedError(
            "FDACRLsFetcher.fetch() is a stub — "
            "implementation pending data-source onboarding."
        )
