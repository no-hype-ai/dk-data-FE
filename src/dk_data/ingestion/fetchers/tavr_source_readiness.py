"""TAVR source readiness — derived gold table.

This is a derived gold table; there is no upstream HTTPS source. The "fetcher"
is a no-op stub that exists only to satisfy the SOURCES registry contract.
All work happens in the loader, which composes the row set from
meta.refresh_log + meta.table_health + hcs_gold.tavr_catalog_candidate_manifest.

Spec: .dk/specs/007-tavr-source-readiness-provisioning/spec.md
"""

import logging
from typing import Any, Dict

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class TavrSourceReadinessFetcher(BaseFetcher):
    """No-op fetcher — this source is derived from meta.* tables in-DB."""

    SOURCE_NAME = "tavr_source_readiness"
    BASE_URL = "internal://meta+hcs_gold"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        logger.info(
            "[%s] derived source — loader reads from meta.refresh_log + "
            "meta.table_health + hcs_gold.tavr_catalog_candidate_manifest in-DB",
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
