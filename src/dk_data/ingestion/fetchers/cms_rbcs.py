"""CMS RBCS (Restructured BETOS Classification System) Fetcher.

Fetches the RBCS classification data mapping HCPCS codes to clinical
categories, subcategories, and families.

Source: https://data.cms.gov/provider-summary-by-type-of-service/provider-service-classifications
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# CMS migrated from slug-based URLs to UUID-based data-api endpoints
DATASET_UUID = "e3db6e56-149f-49ce-b374-40aecda2357b"  # RY2025 latest


class CMSRBCSFetcher(BaseFetcher):
    """Fetcher for the CMS Restructured BETOS Classification System."""

    SOURCE_NAME = "cms_rbcs"
    BASE_URL = "https://data.cms.gov/provider-summary-by-type-of-service/provider-service-classifications"

    def get_latest_url(self) -> str:
        """Return the CMS RBCS data API URL (UUID-based)."""
        uuid = self.params.get("dataset_uuid", DATASET_UUID)
        return f"https://data.cms.gov/data-api/v1/dataset/{uuid}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch RBCS classification records from CMS API.

        Keyword Args:
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            url = self.get_latest_url()
            logger.info("Fetching RBCS data from %s", url)

            records: List[Dict[str, Any]] = []
            offset = kwargs.get('resume_offset', 0)
            page_size = 1000

            while True:
                params = {"offset": offset, "size": page_size}
                self._last_offset = offset
                resp = self.session.get(url, params=params, timeout=60)
                resp.raise_for_status()
                data = resp.json()

                # The UUID-based API returns a JSON list directly,
                # but may also return a dict with a nested list key
                if isinstance(data, dict):
                    data = data.get("data", data.get("results", []))

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
            logger.exception("RBCS fetch failed: %s", exc)
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
        """Extract key fields from an RBCS classification record."""
        hcpcs = item.get("HCPCS_CD") or item.get("hcpcs_code", "")
        if not hcpcs:
            return None

        return {
            "hcpcs_code": hcpcs,
            "rbcs_id": item.get("RBCS_ID") or item.get("rbcs_id"),
            "rbcs_category": item.get("RBCS_CAT") or item.get("rbcs_category"),
            "rbcs_subcategory": item.get("RBCS_SUBCAT") or item.get("rbcs_subcategory"),
            "rbcs_family": item.get("RBCS_FAMILY") or item.get("rbcs_family"),
        }
