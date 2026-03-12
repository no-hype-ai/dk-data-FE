"""CMS Chronic Conditions Prevalence Fetcher.

Fetches Medicare chronic conditions prevalence data from CMS, including
condition-level prevalence rates, beneficiary counts, and per-capita
spending by state.

Source: https://data.cms.gov/medicare-chronic-conditions
"""

import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSChronicConditionsFetcher(BaseFetcher):
    """Fetcher for CMS Medicare Chronic Conditions Prevalence data."""

    SOURCE_NAME = "cms_chronic_conditions"
    BASE_URL = "https://data.cms.gov/medicare-chronic-conditions"

    def get_latest_url(self) -> str:
        """Return the CMS chronic conditions data API URL."""
        year = self.params.get("year", "latest")
        return f"{self.BASE_URL}/data/{year}"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch chronic conditions records from CMS API.

        Keyword Args:
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            url = self.get_latest_url()
            logger.info("Fetching chronic conditions data from %s", url)

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

            content_hash = self.calculate_hash(
                str(len(records)).encode()
            ) if records else None

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "hash": content_hash,
            }
            self.log_fetch_result(result)
            return result

        except Exception as exc:
            logger.exception("Chronic conditions fetch failed: %s", exc)
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
        """Extract key fields from a chronic conditions record."""
        state = item.get("Bene_Geo_Desc") or item.get("state", "")
        condition = item.get("Bene_Cond") or item.get("condition", "")
        if not state or not condition:
            return None

        return {
            "state": state,
            "condition": condition,
            "prevalence_rate": item.get("Prvlnc") or item.get("prevalence_rate"),
            "total_beneficiaries_with_condition": (
                item.get("Bene_Cond_Cnt") or item.get("total_beneficiaries_with_condition")
            ),
            "per_capita_spending": item.get("Per_Capita_Spndng") or item.get("per_capita_spending"),
        }
