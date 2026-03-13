"""CMS Geographic Variation Fetcher.

Fetches Medicare geographic variation data from CMS, including
per-capita spending, utilization rates, and beneficiary counts
broken down by state and county.

Source: https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-geographic-comparisons
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# CMS migrated from slug-based URLs to UUID-based data-api endpoints
DATASET_UUID = "6219697b-8f6c-4164-bed4-cd9317c58ebc"


class CMSGeographicVariationFetcher(BaseFetcher):
    """Fetcher for CMS Medicare Geographic Variation data."""

    SOURCE_NAME = "cms_geographic_variation"
    BASE_URL = "https://data.cms.gov/data-api/v1/dataset"

    def get_latest_url(self) -> str:
        """Return the CMS geographic variation data API URL (UUID-based)."""
        uuid = self.params.get("dataset_uuid", DATASET_UUID)
        return f"{self.BASE_URL}/{uuid}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch geographic variation records from CMS API.

        Keyword Args:
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            url = self.get_latest_url()
            logger.info("Fetching geographic variation data from %s", url)

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
            logger.exception("Geographic variation fetch failed: %s", exc)
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
        """Extract key fields from a geographic variation record."""
        state = (
            item.get("BENE_GEO_DESC") or item.get("State")
            or item.get("state", "")
        )
        if not state:
            return None

        return {
            "state": state,
            "county": item.get("BENE_GEO_CD") or item.get("County") or item.get("county"),
            "total_beneficiaries": (
                item.get("BENES_FFS_CNT") or item.get("Benes_Total")
                or item.get("total_beneficiaries")
            ),
            "total_actual_costs": (
                item.get("TOT_MDCR_STDZD_PYMT_AMT") or item.get("Actual_Per_Capita_Costs")
                or item.get("total_actual_costs")
            ),
            "per_capita_costs": (
                item.get("PER_CAPITA_MDCR_STDZD_PYMT_AMT") or item.get("Per_Capita_Costs")
                or item.get("per_capita_costs")
            ),
            "ip_covered_stays_per_1000": (
                item.get("IP_CVRD_STAYS_PER_1000_BENES") or item.get("IP_Cvrd_Stays_Per_1000")
                or item.get("ip_covered_stays_per_1000")
            ),
            "er_visits_per_1000": (
                item.get("ER_VISITS_PER_1000_BENES") or item.get("ER_Visits_Per_1000")
                or item.get("er_visits_per_1000")
            ),
            "year": item.get("YEAR") or item.get("year"),
        }
