"""CMS NPPES (National Plan and Provider Enumeration System) Fetcher.

Downloads the full NPPES dissemination file (~8GB CSV) with streaming
and chunked parsing. Provides NPI registry data for all healthcare
providers in the United States.

Source: https://download.cms.gov/nppes
"""

import csv
import io
import logging
import zipfile
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Key columns to extract from the full NPPES CSV
NPPES_KEY_FIELDS = [
    "NPI",
    "Entity Type Code",
    "Provider Organization Name (Legal Business Name)",
    "Provider Last Name (Legal Name)",
    "Provider First Name",
    "Provider Credential Text",
    "Provider Enumeration Date",
    "Provider Gender Code",
    "Provider Business Practice Location Address State Name",
    "Provider Business Practice Location Address Postal Code",
    "Provider Business Practice Location Address Telephone Number",
    "Healthcare Provider Taxonomy Code_1",
]

# Normalised output field names
FIELD_MAP = {
    "NPI": "npi",
    "Entity Type Code": "entity_type_code",
    "Provider Organization Name (Legal Business Name)": "provider_organization_name",
    "Provider Last Name (Legal Name)": "provider_last_name",
    "Provider First Name": "provider_first_name",
    "Provider Credential Text": "provider_credential_text",
    "Provider Enumeration Date": "provider_enumeration_date",
    "Provider Gender Code": "provider_gender_code",
    "Provider Business Practice Location Address State Name": "provider_business_practice_location_address_state_name",
    "Provider Business Practice Location Address Postal Code": "provider_business_practice_location_address_postal_code",
    "Provider Business Practice Location Address Telephone Number": "provider_business_practice_location_address_telephone_number",
    "Healthcare Provider Taxonomy Code_1": "healthcare_provider_taxonomy_code_1",
}

# Default chunk size for streaming CSV reads
DEFAULT_CHUNK_SIZE = 50_000


class CMSNPPESFetcher(BaseFetcher):
    """Fetcher for the NPPES bulk CSV dissemination file."""

    SOURCE_NAME = "cms_nppes"
    BASE_URL = "https://download.cms.gov/nppes"

    # NPI Registry API for individual lookups (alternative to bulk)
    NPI_API = "https://npiregistry.cms.hhs.gov/api/?version=2.1"

    # Month names for URL construction
    _MONTHS = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]

    def get_latest_url(self) -> str:
        """Get URL for the latest NPPES full dissemination ZIP file.

        CMS changed the URL pattern from `Full_Replacement.zip` to
        `{Month}_{Year}_V2.zip`.  We construct the URL based on the
        current month or the configured year/month parameters.
        """
        year = self.params.get("year")
        month = self.params.get("month")

        if year and month:
            month_name = self._MONTHS[int(month) - 1] if str(month).isdigit() else month
            return f"{self.BASE_URL}/NPPES_Data_Dissemination_{month_name}_{year}_V2.zip"

        if year:
            return f"{self.BASE_URL}/NPPES_Data_Dissemination_{year}.zip"

        # Default: construct URL for current month
        now = datetime.now()
        month_name = self._MONTHS[now.month - 1]
        return f"{self.BASE_URL}/NPPES_Data_Dissemination_{month_name}_{now.year}_V2.zip"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Download and parse the NPPES bulk CSV.

        The file is ~8 GB compressed.  We stream the download via
        ``download_file``, extract the primary CSV from the ZIP, then
        parse it in chunks to avoid loading everything into memory.

        Keyword Args:
            max_records: Optional cap on the number of records to return.
                         Useful for testing / sampling.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            url = self.get_latest_url()
            timestamp = datetime.now().strftime("%Y%m%d")
            zip_filename = f"nppes_full_{timestamp}.zip"

            logger.info("Downloading NPPES dissemination file from %s", url)
            zip_path = self.download_file(url, zip_filename)
            file_hash = self.calculate_hash(zip_path)

            # Extract and parse the main CSV inside the ZIP
            records = self._parse_zip(zip_path, max_records=max_records)

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "hash": file_hash,
            }
            self.log_fetch_result(result)
            return result

        except Exception as exc:
            logger.exception("NPPES fetch failed: %s", exc)
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
        """Extract and stream-parse the primary CSV from the NPPES ZIP.

        Args:
            zip_path: Path to the downloaded ZIP file.
            max_records: Optional limit on returned records.

        Returns:
            List of normalised record dicts.
        """
        records: List[Dict[str, Any]] = []

        with zipfile.ZipFile(zip_path, "r") as zf:
            # Find the main dissemination CSV (largest file, name contains "npidata")
            csv_name = self._find_main_csv(zf)
            if csv_name is None:
                raise FileNotFoundError("No primary NPPES CSV found inside ZIP")

            logger.info("Parsing %s from ZIP", csv_name)

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

        logger.info("Parsed %d NPPES records", len(records))
        return records

    @staticmethod
    def _find_main_csv(zf: zipfile.ZipFile) -> Optional[str]:
        """Return the name of the main NPI data CSV inside the ZIP."""
        candidates = [
            n for n in zf.namelist()
            if n.lower().endswith(".csv") and "npidata" in n.lower()
        ]
        if not candidates:
            # Fall back to the largest CSV
            csv_files = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not csv_files:
                return None
            candidates = sorted(csv_files, key=lambda n: zf.getinfo(n).file_size, reverse=True)
        return candidates[0]

    @staticmethod
    def _normalise_row(row: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Extract and rename key fields from a raw CSV row."""
        npi = row.get("NPI", "").strip()
        if not npi:
            return None

        record: Dict[str, Any] = {}
        for src_field, dest_field in FIELD_MAP.items():
            value = row.get(src_field, "").strip()
            record[dest_field] = value if value else None
        return record
