"""TAVR public proxy profile — derived gold table for Phase 1B public approximation.

Derived table; no upstream HTTPS source. The "fetcher" is a no-op stub.
The loader joins Phase 1A outputs + HCRIS + Hospital Service Area +
Physician PUF / NPPES / Open Payments to populate a side-by-side
public/licensed/selected schema. Licensed columns are NULL in v1 — the
schema preserves them so Stage 4.5 can layer in licensed overlays without
a schema migration.

Spec: .dk/specs/011-tavr-public-proxy-profile-provisioning/spec.md
"""

import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class TavrPublicProxyProfileFetcher(BaseFetcher):
    """No-op fetcher — this source is derived from Phase 1A gold + physician silver."""

    SOURCE_NAME = "tavr_public_proxy_profile"
    BASE_URL = "internal://hcs_gold+hcs_silver"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        logger.info(
            "[%s] derived source — loader joins tavr_program_year, "
            "tavr_hospital_profile, cms_hcris, cms_hospital_service_area, "
            "cms_physician_puf, cms_nppes, cms_open_payments",
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
