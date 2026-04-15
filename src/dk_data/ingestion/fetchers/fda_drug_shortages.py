"""FDA Drug Shortages fetcher — openFDA Drug Shortages endpoint.

Source: https://api.fda.gov/drug/drugshortages.json
Stores response in mol_raw.fda_drug_shortages.
Feature: 006-claims-engine-data-gaps (T031)
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_OPENFDA_SHORTAGES_URL = "https://api.fda.gov/drug/drugshortages.json"


class FDADrugShortagesFetcher(BaseFetcher):
    """Fetcher for FDA Drug Shortages via openFDA API."""

    SOURCE_NAME = "fda_drug_shortages"
    BASE_URL = "https://api.fda.gov"

    def get_latest_url(self) -> str:
        return _OPENFDA_SHORTAGES_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch drug shortage records from the openFDA API with pagination.

        The openFDA API uses skip/limit pagination with a max of 1000 per page
        and total count in meta.results.total.

        Args:
            max_records: Optional cap on total records fetched.

        Returns:
            Fetch result dictionary with status, records, count, hash.
        """
        max_records: Optional[int] = kwargs.get("max_records")
        api_key = kwargs.get("api_key") or self.params.get("api_key")

        all_records: List[Dict[str, Any]] = []
        skip = 0
        limit = 1000

        try:
            while True:
                if max_records is not None and len(all_records) >= max_records:
                    break

                params: Dict[str, Any] = {"skip": skip, "limit": limit}
                if api_key:
                    params["api_key"] = api_key

                resp = self.session.get(_OPENFDA_SHORTAGES_URL, params=params, timeout=120)
                resp.raise_for_status()
                data = resp.json()

                results = data.get("results", [])
                if not results:
                    break

                all_records.extend(results)
                logger.info(
                    "[%s] Fetched %d records (skip=%d, total=%d)",
                    self.SOURCE_NAME, len(results), skip, len(all_records),
                )

                # Check if we've fetched all available records
                total = data.get("meta", {}).get("results", {}).get("total", 0)
                if len(all_records) >= total:
                    break

                skip += limit

            if max_records is not None:
                all_records = all_records[:max_records]

            content_hash = hashlib.md5(
                str(len(all_records)).encode()
            ).hexdigest()

            result = {
                "status": "success",
                "records": all_records,
                "record_count": len(all_records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(all_records)})
            return result

        except Exception as exc:
            logger.exception("FDADrugShortages fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result
