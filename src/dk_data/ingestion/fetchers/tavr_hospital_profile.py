"""TAVR hospital profile — derived gold table built from existing CMS/HRSA silver layers.

This is a derived gold table; there is no upstream HTTPS source. The "fetcher"
is a no-op stub that satisfies the SOURCES registry contract. The loader
composes rows from the existing CMS Hospital General Info / PoS / HCRIS /
HRSA AHRF / Census CBSA-ZCTA-TIGER / USDA RUCA silver tables already
maintained by dk-data.

Spec: .dk/specs/008-tavr-hospital-profile-provisioning/spec.md
"""

import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class TavrHospitalProfileFetcher(BaseFetcher):
    """No-op fetcher — this source is derived from hcs_silver.* in-DB."""

    SOURCE_NAME = "tavr_hospital_profile"
    BASE_URL = "internal://hcs_silver+meta"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        logger.info(
            "[%s] derived source — loader reads from hcs_silver.* "
            "(cms_hospital_general_info, cms_pos, cms_hcris, hrsa, census, "
            "usda_ruca) and joins to build the gold row set in-DB",
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
