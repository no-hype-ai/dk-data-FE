"""CMS Medicare Plan Formulary Fetcher.

Fetches Medicare Part D plan formulary data from CMS,
including drug tier levels, prior authorization, and quantity limits.

Source: https://data.cms.gov/medicare-part-d-plan-formulary-preference-file
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# CMS migrated from slug-based URLs to UUID-based data-api endpoints
DATASET_UUID = "a94b1015-1b93-476b-80ec-508b4169c8f5"


class CMSFormularyFetcher(BaseFetcher):
    """Fetcher for CMS Medicare Part D Plan Formulary data."""

    SOURCE_NAME = "cms_formulary"
    BASE_URL = "https://data.cms.gov/medicare-part-d-plan-formulary-preference-file"

    def get_latest_url(self) -> str:
        """Return the CMS formulary data API URL (UUID-based)."""
        uuid = self.params.get("dataset_uuid", DATASET_UUID)
        return f"https://data.cms.gov/data-api/v1/dataset/{uuid}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch formulary records from CMS API.

        Keyword Args:
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            url = self.get_latest_url()
            logger.info("Fetching formulary data from %s", url)

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
            logger.exception("Formulary fetch failed: %s", exc)
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
        """Extract key fields from a formulary record."""
        rxcui = item.get("RXCUI") or item.get("rxcui", "")
        if not rxcui:
            return None

        return {
            "contract_id": item.get("CONTRACT_ID") or item.get("contract_id"),
            "plan_id": item.get("PLAN_ID") or item.get("plan_id"),
            "formulary_id": item.get("FORMULARY_ID") or item.get("formulary_id"),
            "rxcui": rxcui,
            "drug_name": item.get("DRUG_NAME") or item.get("drug_name"),
            "tier_level": item.get("TIER_LEVEL_VALUE") or item.get("tier_level"),
            "prior_auth": item.get("PRIOR_AUTHORIZATION") or item.get("prior_auth"),
            "step_therapy": item.get("STEP_THERAPY") or item.get("step_therapy"),
            "quantity_limit": item.get("QUANTITY_LIMIT") or item.get("quantity_limit"),
        }
