"""CMS HCRIS (Hospital Cost Report Information System) Fetcher.

Fetches large cost report CSV files (~1 GB) from CMS via streaming
download. These contain detailed financial worksheet data for all
Medicare-certified hospitals.

Feature: 016-cms-puf-datasource-integration (Phase 3)

Source: https://downloads.cms.gov/files/hcris

Note: The CronJob spec should set a 1Gi memory limit due to file size.
      This fetcher uses streaming download via download_file() to avoid
      loading the entire file into memory.
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
    "fiscal_year_begin",
    "fiscal_year_end",
    "worksheet",
    "line_number",
    "column_number",
    "value",
]

# CMS column mapping from raw HCRIS CSV headers
FIELD_MAP: Dict[str, str] = {
    "PRVDR_NUM": "ccn",
    "FY_BGN_DT": "fiscal_year_begin",
    "FY_END_DT": "fiscal_year_end",
    "WKSHT_CD": "worksheet",
    "LINE_NUM": "line_number",
    "CLMN_NUM": "column_number",
    "ITM_VAL_NUM": "value",
}

# Available fiscal years
AVAILABLE_YEARS = [2020, 2021, 2022, 2023, 2024]


class CMSHCRISFetcher(BaseFetcher):
    """Fetcher for CMS HCRIS cost report data (large file, streaming)."""

    SOURCE_NAME = "cms_hcris"
    BASE_URL = "https://downloads.cms.gov/files/hcris"

    def get_latest_url(self) -> str:
        """Return the download URL for the latest HCRIS file."""
        year = self.params.get("year", max(AVAILABLE_YEARS))
        return f"{self.BASE_URL}/hosp10-{year}-HCRIS.zip"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Download and parse the HCRIS cost report data.

        Uses streaming download via download_file() to handle the
        ~1 GB file size without excessive memory usage.

        Keyword Args:
            year: Fiscal year to fetch (defaults to latest).
            max_records: Optional cap on records (for testing).

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        year = kwargs.get("year") or self.params.get("year", max(AVAILABLE_YEARS))
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            url = self.get_latest_url()
            timestamp = datetime.now().strftime("%Y%m%d")
            zip_filename = f"cms_hcris_{year}_{timestamp}.zip"

            logger.info("Downloading HCRIS file from %s (streaming)", url)
            zip_path = self.download_file(url, zip_filename)
            file_hash = self.calculate_hash(zip_path)

            # Extract and parse the numeric data file
            records = self._parse_zip(zip_path, max_records=max_records)

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "hash": file_hash,
            }
            self.log_fetch_result(result)
            return result

        except Exception as exc:
            logger.exception("HCRIS fetch failed: %s", exc)
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

    def _parse_zip(
        self,
        zip_path,
        max_records: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Extract and stream-parse the HCRIS CSV from the ZIP.

        Args:
            zip_path: Path to the downloaded ZIP file.
            max_records: Optional limit on returned records.

        Returns:
            List of normalised record dicts.
        """
        import io
        import zipfile

        records: List[Dict[str, Any]] = []

        with zipfile.ZipFile(zip_path, "r") as zf:
            # Find the numeric (NMRC) file which has the key financial data
            csv_name = self._find_data_csv(zf)
            if csv_name is None:
                raise FileNotFoundError("No HCRIS data CSV found inside ZIP")

            logger.info("Parsing %s from HCRIS ZIP", csv_name)

            with zf.open(csv_name) as raw:
                text_stream = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
                reader = csv.DictReader(text_stream)

                for row in reader:
                    record = self._normalise_row(row)
                    if record:
                        records.append(record)

                    if max_records and len(records) >= max_records:
                        logger.info("Reached max_records cap (%d)", max_records)
                        break

        logger.info("Parsed %d HCRIS records", len(records))
        return records

    @staticmethod
    def _find_data_csv(zf) -> Optional[str]:
        """Return the name of the primary data CSV inside the ZIP.

        Prefers the NMRC (numeric) file for financial data.
        """
        # Look for numeric data file first
        candidates = [
            n for n in zf.namelist()
            if n.lower().endswith(".csv") and "nmrc" in n.lower()
        ]
        if candidates:
            return candidates[0]

        # Fall back to RPT (report) file
        candidates = [
            n for n in zf.namelist()
            if n.lower().endswith(".csv") and "rpt" in n.lower()
        ]
        if candidates:
            return candidates[0]

        # Fall back to largest CSV
        csv_files = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_files:
            return None
        return sorted(csv_files, key=lambda n: zf.getinfo(n).file_size, reverse=True)[0]

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

        return record
