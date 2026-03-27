"""CMS NDC (National Drug Code) Directory Fetcher.

Fetches drug product data from the FDA NDC Directory API,
providing standardized drug identification codes and product details.

Source: https://open.fda.gov/apis/drug/ndc
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

NDC_KEY_FIELDS = [
    "product_ndc",
    "brand_name",
    "generic_name",
    "labeler_name",
    "dosage_form",
    "route",
    "marketing_category",
    "product_type",
]


class CMSNDCFetcher(BaseFetcher):
    """Fetcher for the FDA NDC Directory via openFDA API."""

    SOURCE_NAME = "cms_ndc"
    BASE_URL = "https://open.fda.gov/apis/drug/ndc"

    def get_latest_url(self) -> str:
        """Return the openFDA NDC endpoint URL."""
        return "https://api.fda.gov/drug/ndc.json"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch NDC directory records from the openFDA API.

        Keyword Args:
            max_records: Optional cap on returned records.
            limit: Per-request page size (max 1000).

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records", 10000)
        limit = kwargs.get("limit", 1000)

        try:
            records: List[Dict[str, Any]] = []
            skip = kwargs.get('resume_offset', 0)
            api_url = self.get_latest_url()

            while True:
                params = {"limit": limit, "skip": skip}
                self._last_offset = skip
                resp = self.session.get(api_url, params=params, timeout=60)
                resp.raise_for_status()
                data = resp.json()

                results = data.get("results", [])
                if not results:
                    break

                for item in results:
                    record = self._normalise(item)
                    if record:
                        records.append(record)

                skip += limit
                if max_records and len(records) >= max_records:
                    records = records[:max_records]
                    break

                # openFDA caps at 26,000 skip
                if skip >= 26000:
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
            logger.exception("NDC fetch failed: %s", exc)
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
        """Extract key fields from an openFDA NDC result."""
        product_ndc = item.get("product_ndc", "").strip()
        if not product_ndc:
            return None

        route_list = item.get("route", [])
        return {
            "product_ndc": product_ndc,
            "brand_name": item.get("brand_name"),
            "generic_name": item.get("generic_name"),
            "labeler_name": item.get("labeler_name"),
            "dosage_form": item.get("dosage_form"),
            "route": route_list[0] if route_list else None,
            "marketing_category": item.get("marketing_category"),
            "product_type": item.get("product_type"),
        }
