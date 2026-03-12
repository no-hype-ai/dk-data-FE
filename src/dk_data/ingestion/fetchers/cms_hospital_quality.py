"""CMS Hospital Star Ratings Fetcher.

Fetches hospital overall quality star ratings and domain-specific
ratings from the CMS Provider Data API.

Feature: 016-cms-puf-datasource-integration (Phase 3)

Source: https://data.cms.gov/provider-data/dataset/hospital-star-ratings
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
    "overall_rating",
    "mortality_rating",
    "safety_rating",
    "readmission_rating",
    "patient_experience_rating",
    "timeliness_rating",
]

# Pagination defaults
DEFAULT_PAGE_SIZE = 500
MAX_PAGES = 200

# Known dataset identifier for Hospital Star Ratings
STAR_RATINGS_DATASET_ID = "hospital-star-ratings"


class CMSHospitalQualityFetcher(BaseFetcher):
    """Fetcher for CMS Hospital Star Ratings data."""

    SOURCE_NAME = "cms_hospital_quality"
    BASE_URL = "https://data.cms.gov/provider-data/dataset/xubh-q36u"

    # Provider Data Catalog API — dataset ID xubh-q36u (Hospital General Information)
    API_ENDPOINT = "https://data.cms.gov/provider-data/api/1/datastore/query/xubh-q36u/0"

    def get_latest_url(self) -> str:
        """Return the API endpoint for hospital star ratings."""
        return f"{self.API_ENDPOINT}?limit={DEFAULT_PAGE_SIZE}&offset=0"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch hospital star ratings via JSON API.

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
            logger.exception("Hospital Quality fetch failed: %s", exc)
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
        """Page through the hospital star ratings API.

        Args:
            max_records: Optional record cap.

        Returns:
            List of normalised record dicts.
        """
        records: List[Dict[str, Any]] = []
        offset = resume_offset
        page_size = DEFAULT_PAGE_SIZE

        while True:
            params: Dict[str, Any] = {"limit": page_size, "offset": offset}
            logger.debug("Fetching Hospital Quality page offset=%d", offset)

            self._last_offset = offset
            try:
                data = self.fetch_json(self.API_ENDPOINT, params=params)
            except Exception as exc:
                logger.warning("Hospital Quality page error at offset %d: %s", offset, exc)
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

        logger.info("Fetched %d Hospital Quality records", len(records))
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
        filename = f"cms_hospital_quality_{timestamp}.json"
        filepath = self.data_dir / filename

        with open(filepath, "w") as fh:
            json.dump(records, fh)

        return self.calculate_hash(filepath)
