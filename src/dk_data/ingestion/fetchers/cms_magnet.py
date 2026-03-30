"""ANCC Magnet Recognition Fetcher.

Downloads the Magnet organization data from the ANCC website via their
Excel download endpoint. The ANCC directory page loads data dynamically
via JavaScript, so HTML scraping does not work. Instead, we use the
direct .xlsx download endpoint.

Feature: 016-cms-puf-datasource-integration (Phase 3)

Source: https://www.nursingworld.org/organizational-programs/magnet
"""

import io
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Key output fields
KEY_FIELDS = [
    "facility_name",
    "city",
    "state",
    "country",
    "designation_year",
    "redesignation_years",
]

# ANCC Excel download endpoint for Magnet organizations
MAGNET_DOWNLOAD_URL = "https://www.nursingworld.org/MapOrganizationBlock/DownloadFormatMapData?type=Magnet"

# Column name mapping from Excel to our schema
COLUMN_MAP = {
    "Facility Name 1": "facility_name",
    "City": "city",
    "State": "state",
    "Country": "country",
    "Zip": "zip_code",
    "Web Address": "web_address",
    "Designation Year": "designation_year",
    "Redesignation Years": "redesignation_years",
    "Address 1": "address_1",
    "Address 2": "address_2",
    "Comments": "comments",
}


class CMSMagnetFetcher(BaseFetcher):
    """Fetcher for ANCC Magnet Recognition data (Excel download)."""

    SOURCE_NAME = "cms_magnet"
    BASE_URL = "https://www.nursingworld.org/organizational-programs/magnet"

    def get_latest_url(self) -> str:
        """Return the URL for the Magnet organization download."""
        return MAGNET_DOWNLOAD_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Download and parse ANCC Magnet designation data from Excel.

        Keyword Args:
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            records = self._download_and_parse(max_records=max_records)
            file_hash = self._save_and_hash(records)

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "hash": file_hash,
            }
            self.log_fetch_result(result)
            return result

        except Exception as exc:
            logger.exception("Magnet fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _download_and_parse(
        self,
        max_records: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Download the Excel file and parse it into records.

        Args:
            max_records: Optional record cap.

        Returns:
            List of Magnet facility record dicts.
        """
        logger.info("Downloading Magnet organizations from %s", MAGNET_DOWNLOAD_URL)
        response = self.session.get(MAGNET_DOWNLOAD_URL, timeout=120)
        response.raise_for_status()

        try:
            import openpyxl
        except ImportError:
            logger.error("openpyxl is required for Magnet Excel parsing")
            raise ImportError(
                "openpyxl is required for Magnet Excel parsing. "
                "Install with: pip install openpyxl"
            )

        wb = openpyxl.load_workbook(io.BytesIO(response.content), read_only=True)
        ws = wb.active

        records: List[Dict[str, Any]] = []
        headers: List[str] = []

        for row_idx, row in enumerate(ws.iter_rows(values_only=True)):
            if row_idx == 0:
                headers = [str(cell).strip() if cell else "" for cell in row]
                continue

            record = self._parse_row(headers, row)
            if record and record.get("facility_name"):
                records.append(record)
                if max_records and len(records) >= max_records:
                    break

        wb.close()
        logger.info("Parsed %d Magnet organizations from Excel", len(records))
        return records

    @staticmethod
    def _parse_row(headers: List[str], row: tuple) -> Optional[Dict[str, Any]]:
        """Parse a single Excel row into a record dict.

        Args:
            headers: Column headers from the first row.
            row: Tuple of cell values.

        Returns:
            Record dict or None if parsing fails.
        """
        try:
            raw = {}
            for i, header in enumerate(headers):
                if i < len(row):
                    mapped_name = COLUMN_MAP.get(header, header.lower().replace(" ", "_"))
                    value = row[i]
                    raw[mapped_name] = str(value).strip() if value is not None else None

            facility_name = raw.get("facility_name")
            if not facility_name:
                return None

            return {
                "facility_name": facility_name,
                "city": raw.get("city"),
                "state": raw.get("state"),
                "country": raw.get("country"),
                "zip_code": raw.get("zip_code"),
                "designation_year": raw.get("designation_year"),
                "redesignation_years": raw.get("redesignation_years"),
                "web_address": raw.get("web_address"),
            }

        except Exception:
            return None

    def _save_and_hash(self, records: List[Dict]) -> Optional[str]:
        """Persist records to a JSON file and return its MD5 hash."""
        import json

        if not records:
            return None

        timestamp = datetime.now().strftime("%Y%m%d")
        filename = f"cms_magnet_{timestamp}.json"
        filepath = self.data_dir / filename

        with open(filepath, "w") as fh:
            json.dump(records, fh)

        return self.calculate_hash(filepath)
