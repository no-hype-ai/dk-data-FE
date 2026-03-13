"""CMS Change of Ownership (CHOW) Fetcher.

Fetches facility change-of-ownership records from the CMS hospitals
and other facilities endpoint. Tracks ownership transitions for
provider facilities.

Feature: 016-cms-puf-datasource-integration (Phase 3)

Source: https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities
"""

import csv
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Key output fields
KEY_FIELDS = [
    "ccn",
    "previous_owner",
    "new_owner",
    "effective_date",
    "provider_type",
]

# Pagination defaults for JSON API fallback
DEFAULT_PAGE_SIZE = 500
MAX_PAGES = 500


class CMSCHOWFetcher(BaseFetcher):
    """Fetcher for CMS Change of Ownership data."""

    SOURCE_NAME = "cms_chow"
    BASE_URL = "https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities"

    # API endpoint (UUID-based — slug endpoints return empty)
    API_ENDPOINT = "https://data.cms.gov/data-api/v1/dataset/c04031db-54ce-461c-85d1-d2613d71f167/data"

    # CSV download fallback
    CSV_URL = "https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/change-of-ownership/data?_format=csv&headers=display"

    def get_latest_url(self) -> str:
        """Return the API endpoint for CHOW data."""
        return self.API_ENDPOINT

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch Change of Ownership records.

        Tries JSON API first, falls back to CSV download.

        Keyword Args:
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            # Method 1: Try JSON API
            records = self._fetch_via_api(max_records=max_records, resume_offset=kwargs.get('resume_offset', 0))

            if not records:
                # Method 2: Fallback to CSV download
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
            logger.exception("CHOW fetch failed: %s", exc)
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

    def _fetch_via_api(
        self,
        max_records: Optional[int] = None,
        resume_offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Fetch via the JSON API with pagination."""
        records: List[Dict[str, Any]] = []
        offset = resume_offset
        page_size = DEFAULT_PAGE_SIZE

        while True:
            params = {"size": page_size, "offset": offset}
            logger.debug("Fetching CHOW API page offset=%d", offset)

            self._last_offset = offset
            try:
                data = self.fetch_json(self.API_ENDPOINT, params=params)
            except Exception as exc:
                logger.warning("CHOW API page error at offset %d: %s", offset, exc)
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

        logger.info("Fetched %d CHOW records via API", len(records))
        return records

    def _fetch_via_csv(
        self,
        max_records: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Fallback: download CSV and parse."""
        timestamp = datetime.now().strftime("%Y%m%d")
        filename = f"cms_chow_{timestamp}.csv"
        filepath = self.download_file(self.CSV_URL, filename)

        records: List[Dict[str, Any]] = []
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                record = self._normalise(row)
                records.append(record)
                if max_records and len(records) >= max_records:
                    break

        logger.info("Parsed %d CHOW records from CSV", len(records))
        return records

    @staticmethod
    def _normalise(row: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key fields from a raw CHOW row.

        The CMS API returns fields like 'CCN - BUYER', 'ORGANIZATION NAME - BUYER'.
        """
        return {
            "ccn": (
                row.get("CCN - BUYER") or row.get("ccn") or ""
            ),
            "previous_owner": (
                row.get("ORGANIZATION NAME - SELLER")
                or row.get("previous_owner")
            ),
            "new_owner": (
                row.get("ORGANIZATION NAME - BUYER")
                or row.get("new_owner")
            ),
            "effective_date": (
                row.get("EFFECTIVE DATE")
                or row.get("effective_date")
            ),
            "provider_type": (
                row.get("PROVIDER TYPE TEXT - BUYER")
                or row.get("provider_type")
            ),
        }

    def _save_and_hash(self, records: List[Dict]) -> Optional[str]:
        """Persist records to a JSON file and return its MD5 hash."""
        import json

        if not records:
            return None

        timestamp = datetime.now().strftime("%Y%m%d")
        filename = f"cms_chow_{timestamp}.json"
        filepath = self.data_dir / filename

        with open(filepath, "w") as fh:
            json.dump(records, fh)

        return self.calculate_hash(filepath)
