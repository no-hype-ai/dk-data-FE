"""CMS Medicare Part B Drug Spending fetcher.

Fetches Medicare Part B drug spending records from the CMS data API.
This dataset provides annual spending, utilization, and pricing data for
drugs administered in outpatient settings under Medicare Part B.

API: https://data.cms.gov/data-api/v1/dataset
  Dataset UUID: 9552b0f5-c65a-4f57-9d2a-a39d9e56e5bc
  Uses BaseFetcher._fetch_cms_api() helper.
  Total: ~50,000 records (drug × year combinations).
  Dedup: generic_name + year combination.

Stores one JSONB record per drug-year row in mol_raw.cms_medicare.
"""

import hashlib
import json
import logging
from typing import Any, Dict, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_DATASET_UUID = "9552b0f5-c65a-4f57-9d2a-a39d9e56e5bc"


class CMSMedicareFetcher(BaseFetcher):
    """Fetcher for CMS Medicare Part B Drug Spending data.

    Uses the BaseFetcher._fetch_cms_api() helper to paginate through the
    CMS data API. Each record is a drug-year spending dict.
    Deduplication at load time is handled by batch insert without conflict
    (each run replaces data via processed_to_bronze flag).
    """

    SOURCE_NAME = "cms_medicare"
    BASE_URL = "https://data.cms.gov/data-api/v1/dataset"

    def get_latest_url(self) -> str:
        return f"{self.BASE_URL}/{_DATASET_UUID}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch CMS Medicare Part B drug spending records.

        Keyword Args:
            max_records: Cap total records. Default: None (all ~50,000).

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: Optional[int] = kwargs.get("max_records")

        try:
            records = self._fetch_cms_api(
                dataset_uuid=_DATASET_UUID,
                max_records=max_records,
            )
            content_hash = hashlib.md5(
                json.dumps(len(records)).encode()
            ).hexdigest()

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except Exception as exc:
            logger.exception("CMS Medicare Part B fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result
