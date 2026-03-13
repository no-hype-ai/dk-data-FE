"""CMS DMEPOS (Durable Medical Equipment, Prosthetics, Orthotics, and Supplies) Fetcher.

Fetches Medicare DMEPOS utilization data from CMS, including
provider-level service counts, charges, and payments by HCPCS code.

Source: https://data.cms.gov/provider-summary-by-type-of-service/medicare-durable-medical-equipment
"""

import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# CMS migrated from slug-based URLs to UUID-based data-api endpoints
DATASET_UUID = "a2d56d3f-3531-4315-9d87-e29986516b41"


class CMSDMEPOSFetcher(BaseFetcher):
    """Fetcher for CMS Medicare DMEPOS Utilization data."""

    SOURCE_NAME = "cms_dmepos"
    BASE_URL = "https://data.cms.gov/data-api/v1/dataset"

    def get_latest_url(self) -> str:
        """Return the CMS DMEPOS data API URL (UUID-based)."""
        uuid = self.params.get("dataset_uuid", DATASET_UUID)
        return f"{self.BASE_URL}/{uuid}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch DMEPOS utilization records from CMS API.

        Keyword Args:
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            url = self.get_latest_url()
            logger.info("Fetching DMEPOS data from %s", url)

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
            logger.exception("DMEPOS fetch failed: %s", exc)
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
        """Extract key fields from a DMEPOS utilization record."""
        npi = item.get("Rndrng_NPI") or item.get("npi", "")
        if not npi:
            return None

        return {
            "npi": npi,
            "hcpcs_code": item.get("HCPCS_Cd") or item.get("hcpcs_code"),
            "hcpcs_description": item.get("HCPCS_Desc") or item.get("hcpcs_description"),
            "total_services": item.get("Tot_Srvcs") or item.get("total_services"),
            "total_beneficiaries": item.get("Tot_Benes") or item.get("total_beneficiaries"),
            "avg_submitted_charge": item.get("Avg_Sbmtd_Chrg") or item.get("avg_submitted_charge"),
            "avg_medicare_payment": item.get("Avg_Mdcr_Pymt_Amt") or item.get("avg_medicare_payment"),
        }
