"""CMS Post-Acute Care Fetcher.

Fetches Medicare post-acute care and hospice data from CMS, including
provider-level episode counts, average payments, and readmission rates.

Source: https://data.cms.gov/provider-summary-by-type-of-service/medicare-post-acute-care-hospice
"""

import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# CMS migrated from slug-based URLs to UUID-based data-api endpoints
DATASET_UUID = "43ef03ce-2b60-40a8-958e-146195b5fec7"


class CMSPostAcuteFetcher(BaseFetcher):
    """Fetcher for CMS Medicare Post-Acute Care and Hospice data."""

    SOURCE_NAME = "cms_post_acute"
    BASE_URL = "https://data.cms.gov/data-api/v1/dataset"

    def get_latest_url(self) -> str:
        """Return the CMS post-acute care data API URL (UUID-based)."""
        uuid = self.params.get("dataset_uuid", DATASET_UUID)
        return f"{self.BASE_URL}/{uuid}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch post-acute care records from CMS API.

        Keyword Args:
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            url = self.get_latest_url()
            logger.info("Fetching post-acute care data from %s", url)

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
            logger.exception("Post-acute care fetch failed: %s", exc)
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
        """Extract key fields from a post-acute care record."""
        ccn = item.get("CCN") or item.get("ccn", "")
        if not ccn:
            return None

        return {
            "ccn": ccn,
            "provider_name": item.get("Provider_Name") or item.get("provider_name"),
            "provider_type": item.get("Provider_Type") or item.get("provider_type"),
            "total_episodes": item.get("Total_Episodes") or item.get("total_episodes"),
            "avg_episode_payment": item.get("Avg_Episode_Payment") or item.get("avg_episode_payment"),
            "readmission_rate": item.get("Readmission_Rate") or item.get("readmission_rate"),
        }
