"""CMS Hospital Care Compare Fetcher.

Fetches hospital quality ratings and general information from the CMS
Provider Data API (Care Compare programme).  The data includes overall
star ratings, ownership details, and facility characteristics.

Source: https://data.cms.gov/provider-data
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
    "zip_code",
    "county_name",
    "phone_number",
    "hospital_type",
    "hospital_ownership",
    "emergency_services",
    "hospital_overall_rating",
]

# CMS Provider Data API pagination defaults
DEFAULT_PAGE_SIZE = 500
MAX_PAGES = 200  # Hospital dataset is ~5-7k rows; 200 pages is generous

# Known dataset identifier for Hospital General Information
HOSPITAL_DATASET_ID = "xubh-q36u"


class CMSCareCompareFetcher(BaseFetcher):
    """Fetcher for CMS Hospital Care Compare data."""

    SOURCE_NAME = "cms_care_compare"
    BASE_URL = "https://data.cms.gov/provider-data/api/1/datastore/sql"

    # Alternative query endpoint
    QUERY_ENDPOINT = (
        "https://data.cms.gov/provider-data/api/1/datastore/query/"
        f"{HOSPITAL_DATASET_ID}/0"
    )

    def get_latest_url(self) -> str:
        """Return the SQL query URL for the hospital dataset."""
        return (
            f"{self.BASE_URL}?query="
            f"[SELECT * FROM {HOSPITAL_DATASET_ID}][LIMIT {DEFAULT_PAGE_SIZE}]"
        )

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch Hospital Care Compare records.

        Attempts the datastore SQL endpoint first, then falls back to
        the query endpoint.

        Keyword Args:
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            # Method 1: SQL datastore endpoint
            records = self._fetch_via_sql(max_records=max_records, resume_offset=kwargs.get('resume_offset', 0))

            if not records:
                # Method 2: Fallback to query endpoint
                logger.info("SQL endpoint returned no data; trying query endpoint")
                records = self._fetch_via_query(max_records=max_records, resume_offset=kwargs.get('resume_offset', 0))

            file_hash = self._save_and_hash(records)

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": file_hash,
            }
            self.log_fetch_result(result)
            return result

        except Exception as exc:
            logger.exception("Care Compare fetch failed: %s", exc)
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

    def _fetch_via_sql(
        self,
        max_records: Optional[int] = None,
        resume_offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Fetch using the CMS datastore SQL endpoint.

        Args:
            max_records: Optional record cap.

        Returns:
            List of normalised record dicts.
        """
        records: List[Dict[str, Any]] = []
        offset = resume_offset
        page_size = DEFAULT_PAGE_SIZE

        while True:
            query = (
                f"[SELECT * FROM {HOSPITAL_DATASET_ID}]"
                f"[LIMIT {page_size} OFFSET {offset}]"
            )
            url = f"{self.BASE_URL}?query={query}"

            logger.debug("Fetching Care Compare SQL page offset=%d", offset)

            try:
                self._last_offset = offset
                response = self.session.get(url, timeout=120)
                response.raise_for_status()
                data = response.json()
            except Exception as exc:
                logger.warning("Care Compare SQL page error at offset %d: %s", offset, exc)
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

        logger.info("Fetched %d Care Compare records via SQL", len(records))
        return records

    def _fetch_via_query(
        self,
        max_records: Optional[int] = None,
        resume_offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Fallback fetch using the query endpoint with limit/offset.

        Args:
            max_records: Optional record cap.

        Returns:
            List of normalised record dicts.
        """
        records: List[Dict[str, Any]] = []
        offset = resume_offset
        page_size = DEFAULT_PAGE_SIZE

        while True:
            params: Dict[str, Any] = {
                "limit": page_size,
                "offset": offset,
            }

            logger.debug("Fetching Care Compare query page offset=%d", offset)

            try:
                self._last_offset = offset
                data = self.fetch_json(self.QUERY_ENDPOINT, params=params)
            except Exception as exc:
                logger.warning("Care Compare query page error at offset %d: %s", offset, exc)
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

        logger.info("Fetched %d Care Compare records via query", len(records))
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
        filename = f"cms_care_compare_{timestamp}.json"
        filepath = self.data_dir / filename

        with open(filepath, "w") as fh:
            json.dump(records, fh)

        return self.calculate_hash(filepath)
