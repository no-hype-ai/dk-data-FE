"""CMS Medicare Physician & Other Practitioners PUF Fetcher.

Fetches the Physician/Supplier Procedure Summary (Public Use File) from
the CMS data.gov API.  The dataset contains information on services and
procedures provided to Medicare beneficiaries by physicians and other
healthcare professionals.

Source: https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# CMS migrated from slug-based URLs to UUID-based data-api endpoints
DATASET_UUID = "92396110-2aed-4d63-a6a2-5d6207d46a29"

# Mapping from CMS API field names to normalised output field names
API_FIELD_MAP = {
    "Rndrng_NPI": "npi",
    "Rndrng_Prvdr_Last_Org_Name": "nppes_provider_last_org_name",
    "Rndrng_Prvdr_First_Name": "nppes_provider_first_name",
    "Rndrng_Prvdr_State_Abrvtn": "nppes_provider_state",
    "Rndrng_Prvdr_Type": "provider_type",
    "HCPCS_Cd": "hcpcs_code",
    "HCPCS_Desc": "hcpcs_description",
    "Place_Of_Srvc": "place_of_service",
    "Tot_Srvcs": "line_srvc_cnt",
    "Tot_Benes": "bene_unique_cnt",
    "Avg_Mdcr_Alowd_Amt": "average_medicare_allowed_amt",
    "Avg_Sbmtd_Chrg": "average_submitted_chrg_amt",
    "Avg_Mdcr_Pymt_Amt": "average_medicare_payment_amt",
}

# Normalised output field names
KEY_FIELDS = list(API_FIELD_MAP.values())

# CMS API pagination defaults
DEFAULT_PAGE_SIZE = 500
MAX_PAGES = 2000  # Safety limit


class CMSPhysicianPUFFetcher(BaseFetcher):
    """Fetcher for the CMS Physician/Supplier PUF data."""

    SOURCE_NAME = "cms_physician_puf"
    BASE_URL = "https://data.cms.gov/data-api/v1/dataset"

    # CMS data-api UUID-based endpoint
    API_ENDPOINT = (
        f"https://data.cms.gov/data-api/v1/dataset/{DATASET_UUID}/data"
    )

    def get_latest_url(self) -> str:
        """Get the API URL for the physician PUF data."""
        year = self.params.get("year")
        if year:
            return f"{self.API_ENDPOINT}?year={year}"
        return self.API_ENDPOINT

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch physician PUF records from the CMS JSON API.

        Paginates through the API collecting all matching records.

        Keyword Args:
            year: Override the data year.
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        year = kwargs.get("year") or self.params.get("year")
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            records = self._fetch_paginated(year=year, max_records=max_records, resume_offset=kwargs.get('resume_offset', 0))
            file_hash = self._save_and_hash(records, year)

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "hash": file_hash,
            }
            self.log_fetch_result(result)
            return result

        except Exception as exc:
            logger.exception("Physician PUF fetch failed: %s", exc)
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
        year: Optional[int] = None,
        max_records: Optional[int] = None,
        resume_offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Page through the CMS JSON API and collect records.

        Args:
            year: Optional year filter.
            max_records: Optional cap.

        Returns:
            List of normalised record dicts.
        """
        records: List[Dict[str, Any]] = []
        offset = resume_offset
        page_size = DEFAULT_PAGE_SIZE

        while True:
            params: Dict[str, Any] = {
                "size": page_size,
                "offset": offset,
            }
            if year:
                params["year"] = year

            logger.debug(
                "Fetching physician PUF page offset=%d size=%d",
                offset,
                page_size,
            )

            self._last_offset = offset
            data = self.fetch_json(self.API_ENDPOINT, params=params)

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

        logger.info("Fetched %d physician PUF records", len(records))
        return records

    @staticmethod
    def _normalise(row: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and normalise key fields from a raw API row.

        The CMS data-api returns fields like Rndrng_NPI, Rndrng_Prvdr_Last_Org_Name, etc.
        We map these to our normalised output field names.
        """
        record: Dict[str, Any] = {}
        for api_field, output_field in API_FIELD_MAP.items():
            # Try the API field name first, then fall back to the output field name
            value = row.get(api_field) or row.get(output_field)
            record[output_field] = value
        return record

    def _save_and_hash(self, records: List[Dict], year: Optional[int] = None) -> Optional[str]:
        """Persist records to a JSON file and return its MD5 hash."""
        import json

        if not records:
            return None

        timestamp = datetime.now().strftime("%Y%m%d")
        year_suffix = f"_{year}" if year else ""
        filename = f"cms_physician_puf{year_suffix}_{timestamp}.json"
        filepath = self.data_dir / filename

        with open(filepath, "w") as fh:
            json.dump(records, fh)

        return self.calculate_hash(filepath)
