"""CMS Part D Drug Spending Fetcher.

Fetches Medicare Part D drug spending summary data from CMS,
including total spending, claims, and beneficiary counts by drug.

Source: https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-medicaid-spending-by-drug
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# CMS migrated from slug-based URLs to UUID-based data-api endpoints
DATASET_UUID = "7e0b4365-fd63-4a29-8f5e-e0ac9f66a81b"  # 2023 annual data
DEFAULT_YEAR = 2023  # Year corresponding to the default dataset UUID


class CMSPartDSpendingFetcher(BaseFetcher):
    """Fetcher for CMS Part D Drug Spending summary data."""

    SOURCE_NAME = "cms_part_d_spending"
    BASE_URL = "https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-medicaid-spending-by-drug"

    def get_latest_url(self) -> str:
        """Return the CMS Part D spending data API URL (UUID-based)."""
        uuid = self.params.get("dataset_uuid", DATASET_UUID)
        return f"https://data.cms.gov/data-api/v1/dataset/{uuid}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch Part D spending records from CMS API.

        Keyword Args:
            max_records: Optional cap on returned records.
            year: Data year to fetch.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            url = self.get_latest_url()
            logger.info("Fetching Part D spending data from %s", url)

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
            logger.exception("Part D spending fetch failed: %s", exc)
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
        """Extract key fields from a Part D spending record.

        The loader (CmsPartDSpendingRecord) expects:
            brand_name, generic_name, total_spending, total_claims,
            total_beneficiaries, avg_cost_per_claim, year
        """
        brand = item.get("Brnd_Name") or item.get("brand_name", "")
        generic = item.get("Gnrc_Name") or item.get("generic_name", "")
        if not brand and not generic:
            return None

        def _first_not_none(*keys):
            for k in keys:
                v = item.get(k)
                if v is not None:
                    return v
            return None

        return {
            "brand_name": brand or None,
            "generic_name": generic or None,
            "total_spending": _first_not_none("Tot_Spndng", "total_spending"),
            "total_claims": _first_not_none("Tot_Clms", "total_claims"),
            "total_beneficiaries": _first_not_none("Tot_Benes", "total_beneficiaries"),
            "avg_cost_per_claim": _first_not_none("Avg_Spnd_Per_Clm", "avg_cost_per_claim"),
            "year": _first_not_none("year", "Year") or DEFAULT_YEAR,
        }
