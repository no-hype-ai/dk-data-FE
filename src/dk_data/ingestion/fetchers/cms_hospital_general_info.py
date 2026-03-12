"""CMS Hospital General Information Fetcher.

Fetches comprehensive hospital demographic and characteristic data
from the CMS Provider Data API, including facility type, ownership,
location, and emergency services availability.

Feature: 016-cms-puf-datasource-integration (Phase 3)

Source: https://data.cms.gov/provider-data/dataset/hospital-general-information
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Key output fields
KEY_FIELDS = [
    "facility_id",
    "facility_name",
    "address",
    "city",
    "state",
    "zip",
    "county",
    "phone",
    "hospital_type",
    "ownership",
    "emergency_services",
]

# Pagination defaults
DEFAULT_PAGE_SIZE = 500
MAX_PAGES = 200

# Known dataset identifier
GENERAL_INFO_DATASET_ID = "xubh-q36u"


class CMSHospitalGeneralInfoFetcher(BaseFetcher):
    """Fetcher for CMS Hospital General Information data."""

    SOURCE_NAME = "cms_hospital_general_info"
    BASE_URL = "https://data.cms.gov/provider-data/dataset/hospital-general-information"

    # Provider Data API endpoint
    API_ENDPOINT = (
        "https://data.cms.gov/provider-data/api/1/datastore/query/"
        f"{GENERAL_INFO_DATASET_ID}/0"
    )

    # Known CSV download URLs
    KNOWN_CSV_URLS = [
        "https://data.cms.gov/provider-data/dataset/xubh-q36u/data.csv",
    ]

    def get_latest_url(self) -> str:
        """Return the API endpoint for hospital general information."""
        return f"{self.API_ENDPOINT}?limit={DEFAULT_PAGE_SIZE}&offset=0"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch hospital general information records.

        Tries JSON API first, falls back to CSV download.

        Keyword Args:
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            # Method 1: Try API
            records = self._fetch_paginated(max_records=max_records, resume_offset=kwargs.get('resume_offset', 0))

            if not records:
                # Method 2: Fallback to CSV
                logger.info("API returned no data; trying CSV download")
                records = self._fetch_via_csv(max_records=max_records)

            file_hash = self._save_and_hash(records)

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "hash": file_hash,
            }
            self.log_fetch_result(result)
            return result

        except Exception as exc:
            logger.exception("Hospital General Info fetch failed: %s", exc)
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
        """Page through the Hospital General Information API."""
        records: List[Dict[str, Any]] = []
        offset = resume_offset
        page_size = DEFAULT_PAGE_SIZE

        while True:
            params: Dict[str, Any] = {"limit": page_size, "offset": offset}
            logger.debug("Fetching Hospital General Info page offset=%d", offset)

            self._last_offset = offset
            try:
                data = self.fetch_json(self.API_ENDPOINT, params=params)
            except Exception as exc:
                logger.warning("Hospital General Info page error at offset %d: %s", offset, exc)
                break

            page_records = data.get("results", []) if isinstance(data, dict) else data

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

        logger.info("Fetched %d Hospital General Info records via API", len(records))
        return records

    def _fetch_via_csv(
        self,
        max_records: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Fallback: download and parse CSV."""
        import csv

        for csv_url in self.KNOWN_CSV_URLS:
            try:
                timestamp = datetime.now().strftime("%Y%m%d")
                filename = f"cms_hospital_general_info_{timestamp}.csv"
                filepath = self.download_file(csv_url, filename)

                records: List[Dict[str, Any]] = []
                with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
                    reader = csv.DictReader(fh)
                    for row in reader:
                        record = self._normalise(row)
                        records.append(record)
                        if max_records and len(records) >= max_records:
                            break

                logger.info("Parsed %d Hospital General Info records from CSV", len(records))
                return records

            except Exception as exc:
                logger.warning("CSV download failed for %s: %s", csv_url, exc)
                continue

        return []

    @staticmethod
    def _normalise(row: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key fields from a raw row."""
        record: Dict[str, Any] = {}
        for field in KEY_FIELDS:
            value = row.get(field) or row.get(field.upper()) or row.get(field.lower())
            # Also try common CMS variations
            if value is None:
                alt_key = field.replace("_", " ").title()
                value = row.get(alt_key)
            record[field] = value
        return record

    def _save_and_hash(self, records: List[Dict]) -> Optional[str]:
        """Persist records to a JSON file and return its MD5 hash."""
        import json

        if not records:
            return None

        timestamp = datetime.now().strftime("%Y%m%d")
        filename = f"cms_hospital_general_info_{timestamp}.json"
        filepath = self.data_dir / filename

        with open(filepath, "w") as fh:
            json.dump(records, fh)

        return self.calculate_hash(filepath)
