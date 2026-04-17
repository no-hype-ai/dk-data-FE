"""CMS Medicare Part D Quarterly Drug Spending fetcher.

The CMS annual Part D Spending by Drug dataset is refreshed with ~2-year lag
and currently contains only CY2019–2023 wide-format columns.

The CMS *Quarterly* Part D Spending by Drug dataset is refreshed every quarter
and currently contains CY2024 (Q1-Q4) and CY2025 (Q1-Q2) data in long format.

API: https://data.cms.gov/data-api/v1/dataset
  Dataset UUID: b4d19308-eba3-430e-a994-063197c3aef5 (Quarterly Part D)
  Last refreshed: 2026-01-29

Column schema (long format):
  Brnd_Name, Gnrc_Name, Tot_Mftr, Mftr_Name, Year (e.g. "2024 (Q1-Q4)"),
  Tot_Benes, Tot_Clms, Tot_Spndng, Avg_Spnd_Per_Bene, Avg_Spnd_Per_Clm,
  Drug_Uses

Note: Each drug has multiple rows — one "Overall" row and one per manufacturer.
For drug-level analysis filter to Mftr_Name == 'Overall' to avoid double-counting.
"""

import hashlib
import json
import logging
from typing import Any, Dict, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_DATASET_UUID = "b4d19308-eba3-430e-a994-063197c3aef5"


class CMSPartDSpendingQuarterlyFetcher(BaseFetcher):
    """Fetcher for CMS Medicare Quarterly Part D Drug Spending data."""

    SOURCE_NAME = "cms_part_d_spending_quarterly"
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
            logger.exception("CMS Part D Quarterly fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result
