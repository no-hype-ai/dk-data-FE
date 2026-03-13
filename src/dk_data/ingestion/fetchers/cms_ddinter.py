"""CMS DDInter (Drug-Drug Interaction) Fetcher.

Fetches drug-drug interaction data from the DDInter API,
providing interaction type, severity, and descriptions.

Source: https://ddinter.scbdd.com/api
"""

import logging
from typing import Any, Dict, List, Optional

import urllib3

from .base import BaseFetcher

# DDInter server has an expired SSL certificate as of 2026-03.
# Suppress the InsecureRequestWarning when using verify=False.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class CMSDDInterFetcher(BaseFetcher):
    """Fetcher for Drug-Drug Interaction data from DDInter API."""

    SOURCE_NAME = "cms_ddinter"
    BASE_URL = "https://ddinter.scbdd.com/api"

    def get_latest_url(self) -> str:
        """Return the DDInter API base URL."""
        return f"{self.BASE_URL}/interactions"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch drug-drug interaction records from DDInter API.

        Keyword Args:
            max_records: Optional cap on returned records.
            drug_names: Optional list of drug names to query interactions for.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records", 5000)
        drug_names: Optional[List[str]] = kwargs.get("drug_names") or self.params.get("drug_names")

        try:
            url = self.get_latest_url()
            logger.info("Fetching drug-drug interactions from %s", url)
            logger.warning(
                "Using verify=False for DDInter API (expired SSL cert on ddinter.scbdd.com)"
            )

            records: List[Dict[str, Any]] = []
            page = 1
            page_size = 100

            while True:
                params = {"page": page, "per_page": page_size}
                if drug_names:
                    params["drug"] = ",".join(drug_names)

                resp = self.session.get(url, params=params, timeout=60, verify=False)
                resp.raise_for_status()
                data = resp.json()

                results = data if isinstance(data, list) else data.get("results", data.get("data", []))
                if not results:
                    break

                for item in results:
                    record = self._normalise(item)
                    if record:
                        records.append(record)

                if len(results) < page_size:
                    break

                page += 1
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
            logger.exception("DDInter fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    @staticmethod
    def _normalise(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract key fields from a DDInter interaction record."""
        drug_a = item.get("drug_a") or item.get("Drug_A", "")
        drug_b = item.get("drug_b") or item.get("Drug_B", "")
        if not drug_a or not drug_b:
            return None

        return {
            "drug_a": drug_a,
            "drug_b": drug_b,
            "interaction_type": item.get("interaction_type") or item.get("Level"),
            "severity": item.get("severity") or item.get("Severity"),
            "description": item.get("description") or item.get("Description"),
        }
