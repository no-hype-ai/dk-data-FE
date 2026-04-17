"""CMS Medicare Part B Quarterly Drug Spending fetcher.

The CMS annual Part B Spending by Drug dataset (UUID 76a714ad-...) is released
with approximately a 2-year lag — as of 2026-04 it only contains CY2019–2023
wide-format columns (Tot_Spndng_2019 ... Tot_Spndng_2023).

The CMS *Quarterly* Part B Spending by Drug dataset is refreshed every quarter
and currently contains CY2024 (Q1-Q4) and CY2025 (Q1-Q2) data in long format
(one row per drug × year with a ``Year`` string column). Ingesting this closes
the 2024-2025 coverage gap without waiting for CMS to publish the annual file.

API: https://data.cms.gov/data-api/v1/dataset
  Dataset UUID: bf6a5b3b-31ee-4abb-b1ad-2607a1e7510a (Quarterly Part B)
  Dataset UUID: a1a44b5d-d5c4-4e00-9426-c4bc9e67d82e (alternate – verify)
  Last refreshed: 2026-01-29 (see data.cms.gov/data.json catalog)

Column schema (long format):
  Brnd_Name, Gnrc_Name, HCPCS_Cd, HCPCS_Desc, Year (e.g. "2024 (Q1-Q4)"),
  Tot_Benes, Tot_Clms, Tot_Spndng, Avg_Spnd_Per_Bene, Avg_Spnd_Per_Clm
"""

import hashlib
import json
import logging
from typing import Any, Dict, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_DATASET_UUID = "bf6a5b3b-31ee-4abb-b1ad-2607a1e7510a"


class CMSPartBSpendingQuarterlyFetcher(BaseFetcher):
    """Fetcher for CMS Medicare Quarterly Part B Drug Spending data."""

    SOURCE_NAME = "cms_part_b_spending_quarterly"
    BASE_URL = "https://data.cms.gov/data-api/v1/dataset"
    DATASET_UUID = _DATASET_UUID

    def get_latest_url(self) -> str:
        return f"{self.BASE_URL}/{_DATASET_UUID}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        max_records: Optional[int] = kwargs.get("max_records")
        try:
            records = self._fetch_cms_api(
                dataset_uuid=_DATASET_UUID,
                max_records=max_records,
            )
            content_hash = hashlib.md5(json.dumps(len(records)).encode()).hexdigest()
            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result
        except Exception as exc:
            logger.exception("CMS Part B Quarterly fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result
