"""CMS Provider of Services (POS) File Fetcher.

Fetches facility-level data from the CMS Provider of Services file,
including hospital demographics, bed counts, and ownership information.

Feature: 016-cms-puf-datasource-integration (Phase 3)

Source: https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/provider-of-services-file
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
    "facility_name",
    "street_address",
    "city",
    "state",
    "zip_code",
    "provider_type",
    "beds",
    "ownership_type",
]

# CMS column mapping from raw POS headers to normalised field names
FIELD_MAP: Dict[str, str] = {
    "PRVDR_NUM": "ccn",
    "FAC_NAME": "facility_name",
    "ST_ADR": "street_address",
    "CITY_NAME": "city",
    "STATE_CD": "state",
    "ZIP_CD": "zip_code",
    "PRVDR_CTGRY_CD": "provider_type",
    "BED_CNT": "beds",
    "GNRL_CNTL_TYPE_CD": "ownership_type",
}


class CMSPOSFetcher(BaseFetcher):
    """Fetcher for the CMS Provider of Services file."""

    SOURCE_NAME = "cms_pos"
    BASE_URL = "https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/provider-of-services-file"

    # CMS migrated POS to UUID-based data-api endpoints
    # Hospital & Non-Hospital Facilities dataset
    DATASET_UUIDS = {
        "hospital": "4bdd6342-510f-42fd-9a75-3068e84d80ec",  # Q2 2025 Hospital & Non-Hospital
        "iqies": "8ba0f9b4-9493-4aa0-9f82-44ea9468d1b5",     # Q4 2025 iQIES
    }
    DEFAULT_UUID = "4bdd6342-510f-42fd-9a75-3068e84d80ec"

    def get_latest_url(self) -> str:
        """Return the download URL for the latest POS file (UUID-based API or CSV)."""
        uuid = self.params.get("dataset_uuid", self.DEFAULT_UUID)
        return f"https://data.cms.gov/data-api/v1/dataset/{uuid}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch CMS Provider of Services records via JSON API.

        Falls back to CSV download if a direct file URL is configured.

        Keyword Args:
            max_records: Optional cap on the number of records to return.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        import hashlib as _hashlib

        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            url = self.get_latest_url()
            logger.info("Fetching CMS POS data from %s", url)

            records: List[Dict[str, Any]] = []
            offset = kwargs.get('resume_offset', 0)
            page_size = 1000

            while True:
                params = {"offset": offset, "size": page_size}
                self._last_offset = offset
                resp = self.session.get(url, params=params, timeout=120)
                resp.raise_for_status()
                data = resp.json()

                if not data:
                    break

                for item in data:
                    record = self._normalise_json(item)
                    if record:
                        records.append(record)

                if len(data) < page_size:
                    break

                offset += page_size
                if max_records and len(records) >= max_records:
                    records = records[:max_records]
                    break

            content_hash = _hashlib.md5(
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
            logger.exception("CMS POS fetch failed: %s", exc)
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

    def _parse_csv(
        self,
        filepath,
        max_records: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Parse the POS CSV and normalise field names.

        Args:
            filepath: Path to the downloaded CSV file.
            max_records: Optional limit on returned records.

        Returns:
            List of normalised record dicts.
        """
        records: List[Dict[str, Any]] = []

        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                record = self._normalise_row(row)
                if record:
                    records.append(record)
                if max_records and len(records) >= max_records:
                    break

        logger.info("Parsed %d CMS POS records", len(records))
        return records

    @staticmethod
    def _normalise_json(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract and rename key fields from a JSON API record."""
        ccn = (item.get("PRVDR_NUM") or item.get("ccn") or item.get("provider_number", "")).strip()
        if not ccn:
            return None

        return {
            "ccn": ccn,
            "facility_name": item.get("FAC_NAME") or item.get("facility_name"),
            "street_address": item.get("ST_ADR") or item.get("street_address"),
            "city": item.get("CITY_NAME") or item.get("city"),
            "state": item.get("STATE_CD") or item.get("state"),
            "zip_code": item.get("ZIP_CD") or item.get("zip_code"),
            "provider_type": item.get("PRVDR_CTGRY_CD") or item.get("provider_type"),
            "beds": item.get("BED_CNT") or item.get("beds"),
            "ownership_type": item.get("GNRL_CNTL_TYPE_CD") or item.get("ownership_type"),
        }

    @staticmethod
    def _normalise_row(row: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Extract and rename key fields from a raw CSV row."""
        ccn = (row.get("PRVDR_NUM") or row.get("ccn", "")).strip()
        if not ccn:
            return None

        record: Dict[str, Any] = {}
        for src_field, dest_field in FIELD_MAP.items():
            value = row.get(src_field, "").strip()
            record[dest_field] = value if value else None

        # Also try direct field names (some POS files use display headers)
        if record.get("ccn") is None:
            for field in KEY_FIELDS:
                if record.get(field) is None:
                    value = row.get(field, "").strip() if row.get(field) else None
                    if value:
                        record[field] = value

        return record
