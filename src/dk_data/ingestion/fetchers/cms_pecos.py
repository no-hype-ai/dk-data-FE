"""CMS PECOS (Provider Enrollment, Chain, and Ownership System) Fetcher.

Fetches Medicare provider/supplier enrollment data from the PECOS API.
Provides NPI-to-organization linkage and enrollment status.

Feature: 016-cms-puf-datasource-integration (Phase 3)

Source: https://data.cms.gov/provider-characteristics/medicare-provider-supplier-enrollment
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Key output fields
KEY_FIELDS = [
    "enrollment_id",
    "npi",
    "organization_name",
    "org_npi",
    "state",
    "enrollment_type",
    "enrollment_date",
]

# Pagination defaults
DEFAULT_PAGE_SIZE = 500
MAX_PAGES = 2000


class CMSPECOSFetcher(BaseFetcher):
    """Fetcher for CMS PECOS Medicare enrollment data."""

    SOURCE_NAME = "cms_pecos"
    BASE_URL = "https://data.cms.gov/provider-characteristics/medicare-provider-supplier-enrollment"

    # API endpoint for data access
    API_ENDPOINT = "https://data.cms.gov/data-api/v1/dataset/medicare-provider-supplier-enrollment/data"

    def get_latest_url(self) -> str:
        """Return the API endpoint for PECOS data."""
        return f"{self.API_ENDPOINT}?size={DEFAULT_PAGE_SIZE}&offset=0"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch PECOS enrollment records via paginated JSON API.

        Keyword Args:
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            records = self._fetch_paginated(max_records=max_records, resume_offset=kwargs.get('resume_offset', 0))
            file_hash = self._save_and_hash(records)

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "hash": file_hash,
            }
            self.log_fetch_result(result)
            return result

        except Exception as exc:
            logger.exception("PECOS fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "hash": None,
                "error": str(exc),
                "last_offset": getattr(self, '_last_offset', 0),
            }
            self.log_fetch_result(result)
            return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_paginated(
        self,
        max_records: Optional[int] = None,
        resume_offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Page through the PECOS API endpoint.

        Args:
            max_records: Optional record cap.

        Returns:
            List of normalised record dicts.
        """
        records: List[Dict[str, Any]] = []
        offset = resume_offset
        page_size = DEFAULT_PAGE_SIZE

        while True:
            params = {"size": page_size, "offset": offset}
            logger.debug("Fetching PECOS page offset=%d", offset)

            self._last_offset = offset
            try:
                data = self.fetch_json(self.API_ENDPOINT, params=params)
            except Exception as exc:
                logger.warning("PECOS page fetch error at offset %d: %s", offset, exc)
                break

            page_records = data if isinstance(data, list) else data.get("results", data.get("data", []))

            if not page_records:
                break

            for row in page_records:
                record = self._normalise(row)
                records.append(record)

            if max_records and len(records) >= max_records:
                records = records[:max_records]
                break

            if len(page_records) < page_size:
                break

            offset += page_size

            if offset // page_size >= MAX_PAGES:
                logger.warning("Reached pagination safety limit (%d pages)", MAX_PAGES)
                break

        logger.info("Fetched %d PECOS records", len(records))
        return records

    @staticmethod
    def _normalise(row: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key fields from a raw API row."""
        record: Dict[str, Any] = {}
        for field in KEY_FIELDS:
            value = row.get(field) or row.get(field.upper()) or row.get(field.lower())
            record[field] = value
        return record

    def _save_and_hash(self, records: List[Dict]) -> Optional[str]:
        """Persist records to a JSON file and return its MD5 hash."""
        import json

        if not records:
            return None

        timestamp = datetime.now().strftime("%Y%m%d")
        filename = f"cms_pecos_{timestamp}.json"
        filepath = self.data_dir / filename

        with open(filepath, "w") as fh:
            json.dump(records, fh)

        return self.calculate_hash(filepath)
