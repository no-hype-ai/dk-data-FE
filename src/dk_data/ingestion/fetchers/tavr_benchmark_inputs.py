"""TAVR benchmark inputs — derived gold table joining Phase 1A outputs + adjustment context.

Derived table; no upstream HTTPS source. The "fetcher" is a no-op stub.
The loader joins hcs_gold.tavr_hospital_profile + hcs_gold.tavr_program_year
(own Phase 1A outputs) with CMS Hospital Service Area + MSPB / VBP / HRRP /
HAC silver tables for payment-adjustment context.

Spec: .dk/specs/010-tavr-benchmark-inputs-provisioning/spec.md
"""

import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class TavrBenchmarkInputsFetcher(BaseFetcher):
    """No-op fetcher — this source is derived from Phase 1A gold + adjustment silver."""

    SOURCE_NAME = "tavr_benchmark_inputs"
    BASE_URL = "internal://hcs_gold+hcs_silver"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        logger.info(
            "[%s] derived source — loader joins tavr_hospital_profile, "
            "tavr_program_year, cms_hospital_service_area, cms_mspb, "
            "cms_vbp, cms_hrrp, cms_hac_reduction",
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
