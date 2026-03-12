"""CMS Part B Drug Spending Fetcher.

Fetches Medicare Part B drug spending data from CMS,
including HCPCS-level spending, claims, and beneficiary counts.

Source: https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-medicaid-spending-by-drug
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# CMS migrated from slug-based URLs to UUID-based data-api endpoints
DATASET_UUID = "76a714ad-3a2c-43ac-b76d-9dadf8f7d890"  # 2023 annual data


class CMSPartBSpendingFetcher(BaseFetcher):
    """Fetcher for CMS Part B Drug Spending data."""

    SOURCE_NAME = "cms_part_b_spending"
    BASE_URL = "https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-medicaid-spending-by-drug"

    def get_latest_url(self) -> str:
        """Return the CMS Part B spending data API URL (UUID-based)."""
        uuid = self.params.get("dataset_uuid", DATASET_UUID)
        return f"https://data.cms.gov/data-api/v1/dataset/{uuid}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch Part B spending records from CMS API.

        Keyword Args:
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            url = self.get_latest_url()
            logger.info("Fetching Part B spending data from %s", url)

            records: List[Dict[str, Any]] = []
            offset = kwargs.get('resume_offset', 0)
            page_size = 1000

            while True:
                params = {"offset": offset, "size": page_size}
                self._last_offset = offset
                resp = self.session.get(url, params=params, timeout=60)
                resp.raise_for_status()
                data = resp.json()

                if not data:
                    break

                for item in data:
                    record = self._normalise(item)
                    if record:
                        records.append(record)

                if len(data) < page_size:
                    break

                offset += page_size
                if max_records and len(records) >= max_records:
                    records = records[:max_records]
                    break

            content_hash = hashlib.md5(
                str(len(records)).encode()
            ).hexdigest() if records else None

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "hash": content_hash,
            }
            self.log_fetch_result(result)
            return result

        except Exception as exc:
            logger.exception("Part B spending fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "hash": None,
                "error": str(exc),
                "last_offset": getattr(self, '_last_offset', 0),
            }
            self.log_fetch_result(result)
            return result

    @staticmethod
    def _normalise(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract key fields from a Part B spending record."""
        hcpcs = item.get("HCPCS_Cd") or item.get("hcpcs_code", "")
        if not hcpcs:
            return None

        return {
            "hcpcs_code": hcpcs,
            "hcpcs_description": item.get("HCPCS_Desc") or item.get("hcpcs_description"),
            "total_spending": item.get("Tot_Spndng") or item.get("total_spending"),
            "total_claims": item.get("Tot_Clms") or item.get("total_claims"),
            "total_beneficiaries": item.get("Tot_Benes") or item.get("total_beneficiaries"),
            "avg_cost_per_claim": item.get("Avg_Spnd_Per_Clm") or item.get("avg_cost_per_claim"),
            "year": item.get("year") or item.get("Year"),
        }
