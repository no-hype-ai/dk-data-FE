"""Treatment Guidelines Fetcher — manual curation pipeline stub.

Feature: 006-claims-engine-data-gaps (Item 8, T051)

This fetcher is a placeholder for the treatment guidelines data pipeline.
Treatment guidelines are curated manually on a quarterly cadence by the
clinical data team. The curation process involves:

  1. Identifying new or updated guidelines from professional societies
     (e.g., NCCN, AAN, ACC/AHA, IDSA, NICE) and regulatory bodies.
  2. Extracting structured recommendation data (indications, evidence
     grades, treatment algorithms) from published PDFs/HTML.
  3. Mapping indications to ICD-11 codes for crosswalk to ind_silver.conditions.
  4. Loading curated records into mol_raw.guidelines via this pipeline.

Quarterly maintenance cadence:
  - Q1 (Jan): Full refresh of oncology and immunology guidelines
  - Q2 (Apr): Full refresh of cardiology and neurology guidelines
  - Q3 (Jul): Full refresh of infectious disease and endocrine guidelines
  - Q4 (Oct): Full refresh of all remaining therapeutic areas + annual audit

Until the curation pipeline is automated, records are loaded via bulk
INSERT from vetted spreadsheets. This fetcher returns an empty result
set and is registered in the scheduler for future automation.

Target table: mol_raw.guidelines (migration 240)
"""

import logging
from typing import Any, Dict, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class GuidelinesFetcher(BaseFetcher):
    """Stub fetcher for treatment guidelines — manual curation pipeline.

    Returns an empty result set. Actual data is loaded via quarterly
    manual curation (see module docstring for cadence details).
    """

    SOURCE_NAME = "guidelines"
    BASE_URL = ""

    def get_latest_url(self) -> str:
        """No automated source URL — guidelines are manually curated."""
        return ""

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Return empty result set (manual curation pipeline).

        This stub exists to register the guidelines source in the
        ingestion scheduler. Data is loaded via bulk INSERT from
        curated spreadsheets on a quarterly cadence.

        Returns:
            Dict with status='success' and zero records.
        """
        logger.info(
            "Guidelines fetcher invoked — this is a manual curation pipeline. "
            "Load data via bulk INSERT into mol_raw.guidelines."
        )

        result: Dict[str, Any] = {
            "status": "success",
            "records": [],
            "record_count": 0,
            "hash": None,
        }
        self.log_fetch_result(result)
        return result
