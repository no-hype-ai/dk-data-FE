"""CMS Medicare-Medicaid Dual Enrollment fetcher.

The published file (MDCR ENROLL AB 40-48_CPS_02ENR_2023.zip) contains a multi-sheet
formatted Excel workbook with pivot-style enrollment tables — NOT a flat CSV/tabular
export. The sheets use merged cells, descriptive headers, and aggregated sub-totals
that don't map directly to the simple row format the source loader expects.

To load this data requires a custom XLSX parser that:
  1. Identifies the state-level summary sheet (MDCR ENROLL AB 48)
  2. Skips title rows and parses the "Area of Residence" column as state_name
  3. Maps the aggregated count columns to: tot_benes, dual_elgbl_full_benes, etc.

Until that parser is implemented, this source remains a file-based stub.
Use --file with ingestion.main once a normalized CSV is prepared from the XLSX.

Download URL (2023 data, 74.6 KB ZIP):
  https://data.cms.gov/sites/default/files/2025-09/1104c73c-6cb7-422c-bb24-73236d1b5767/MDCR%20ENROLL%20AB%2040-48_CPS_02ENR_2023.zip
"""
import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSDualEligibleFetcher(BaseFetcher):
    SOURCE_NAME = "cms_dual_eligible"
    BASE_URL = (
        "https://data.cms.gov/sites/default/files/2025-09/"
        "1104c73c-6cb7-422c-bb24-73236d1b5767/"
        "MDCR%20ENROLL%20AB%2040-48_CPS_02ENR_2023.zip"
    )

    def get_latest_url(self) -> str:
        return self.BASE_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """File is a formatted Excel workbook; custom parser required before loading."""
        logger.info(
            "cms_dual_eligible: source is a multi-sheet formatted Excel workbook. "
            "Custom XLSX parser needed. Download from: %s",
            self.BASE_URL,
        )
        return {"status": "source_unavailable", "records": [], "record_count": 0, "hash": None,
                "error": "Formatted Excel workbook requires custom parser — not yet implemented"}
