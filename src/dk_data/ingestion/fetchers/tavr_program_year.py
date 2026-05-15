"""TAVR program-year — derived gold table built from CMS Inpatient PUF silver layers.

Derived table; no upstream HTTPS source. The "fetcher" is a no-op stub.
The loader composes (ccn × year) rows from existing CMS Inpatient PUF silver
tables filtered to DRG 266 + 267 (TAVR-relevant MS-DRGs).

Spec: .dk/specs/009-tavr-program-year-provisioning/spec.md
"""

import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class TavrProgramYearFetcher(BaseFetcher):
    """No-op fetcher — this source is derived from hcs_silver.cms_inpatient_puf."""

    SOURCE_NAME = "tavr_program_year"
    BASE_URL = "internal://hcs_silver.cms_inpatient_puf"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        logger.info(
            "[%s] derived source — loader filters hcs_silver.cms_inpatient_puf "
            "to DRG 266/267, aggregates per (ccn, year), joins to "
            "cms_inpatient_geo for percentiles",
            self.SOURCE_NAME,
        )
        return {
            "status": "success",
            "records": [{"_derived": True}],
            "record_count": 1,
            "hash": None,
        }

    def get_latest_url(self) -> str:
        return self.BASE_URL
