"""CMS Chronic Conditions Prevalence Fetcher.

Fetches Medicare chronic conditions prevalence data from CMS, including
condition-level prevalence rates, beneficiary counts, and per-capita
spending by state.

NOTE: The CMS Chronic Conditions dataset is NOT available through the
standard CMS data-api/UUID pattern. It has been removed from the CMS
open data catalog. This fetcher attempts to download the data from the
CMS Specific Chronic Conditions CSV endpoint. If CMS re-publishes the
data under a UUID, set params["dataset_uuid"] to use the API instead.

Source: https://data.cms.gov/medicare-chronic-conditions
"""

import csv
import hashlib
import io
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Known CMS CSV download URLs for chronic conditions data.
# CMS publishes these as static files; URLs change when data is updated.
CHRONIC_CONDITIONS_CSV_URLS = [
    "https://data.cms.gov/sites/default/files/2023-04/67b25b4e-0423-4ee1-b821-8fd06e6e8a4a/Specific_Chronic_Conditions_by_Geography.csv",
    "https://data.cms.gov/sites/default/files/2024-01/Specific_Chronic_Conditions_by_Geography.csv",
]

# CMS data-api endpoint (if a UUID becomes available)
DEFAULT_DATASET_UUID = ""


class CMSChronicConditionsFetcher(BaseFetcher):
    """Fetcher for CMS Medicare Chronic Conditions Prevalence data."""

    SOURCE_NAME = "cms_chronic_conditions"
    BASE_URL = "https://data.cms.gov/data-api/v1/dataset"

    def get_latest_url(self) -> str:
        """Return the CMS chronic conditions data URL."""
        uuid = self.params.get("dataset_uuid", DEFAULT_DATASET_UUID)
        if uuid:
            return f"{self.BASE_URL}/{uuid}/data"
        # Fall back to CSV download
        return CHRONIC_CONDITIONS_CSV_URLS[0]

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch chronic conditions records from CMS.

        Tries the UUID-based API first (if configured), then falls back
        to CSV download URLs.

        Keyword Args:
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            uuid = self.params.get("dataset_uuid", DEFAULT_DATASET_UUID)

            if uuid:
                records = self._fetch_from_api(uuid, max_records=max_records,
                                               resume_offset=kwargs.get('resume_offset', 0))
            else:
                records = self._fetch_from_csv(max_records=max_records)

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

    def _fetch_from_api(self, uuid: str, max_records: Optional[int] = None,
                        resume_offset: int = 0) -> List[Dict[str, Any]]:
        """Fetch via the CMS data-api (UUID-based)."""
        url = f"{self.BASE_URL}/{uuid}/data"
        logger.info("Fetching chronic conditions data from API: %s", url)

        records: List[Dict[str, Any]] = []
        offset = resume_offset
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

        return records

    def _fetch_from_csv(self, max_records: Optional[int] = None) -> List[Dict[str, Any]]:
        """Download and parse chronic conditions CSV from CMS."""
        csv_url = self.params.get("csv_url")
        urls_to_try = [csv_url] if csv_url else CHRONIC_CONDITIONS_CSV_URLS

        for url in urls_to_try:
            if not url:
                continue
            try:
                logger.info("Trying chronic conditions CSV: %s", url)
                resp = self.session.get(url, timeout=120)
                if resp.status_code == 404:
                    logger.debug("CSV URL returned 404: %s", url)
                    continue
                resp.raise_for_status()
                return self._parse_csv(resp.text, max_records=max_records)
            except Exception as exc:
                logger.debug("CSV download failed for %s: %s", url, exc)
                continue

        logger.warning(
            "CMS Chronic Conditions: no working data source found. "
            "The dataset is not available through the CMS data API or known CSV URLs. "
            "Set params['dataset_uuid'] if CMS re-publishes it, or "
            "set params['csv_url'] to a direct download link."
        )
        return []

    def _parse_csv(self, csv_text: str, max_records: Optional[int] = None) -> List[Dict[str, Any]]:
        """Parse chronic conditions CSV text into records."""
        records: List[Dict[str, Any]] = []
        reader = csv.DictReader(io.StringIO(csv_text))

        for row in reader:
            record = self._normalise(row)
            if record:
                records.append(record)
                if max_records and len(records) >= max_records:
                    break

        logger.info("Parsed %d chronic conditions records from CSV", len(records))
        return records

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
