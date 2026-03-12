"""CMS Inpatient PUF (DRG Volumes) Fetcher.

Fetches inpatient hospital DRG-level utilization data from the CMS
Medicare Inpatient Hospitals dataset. Provides procedure volumes,
charges, and payment data at the provider/DRG level.

Feature: 016-cms-puf-datasource-integration (Phase 3)

Source: https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Key output fields
KEY_FIELDS = [
    "ccn",
    "drg_code",
    "drg_description",
    "total_discharges",
    "avg_covered_charges",
    "avg_total_payments",
    "avg_medicare_payments",
]

# CMS column mapping from API response to normalised fields
FIELD_MAP: Dict[str, str] = {
    "Rndrng_Prvdr_CCN": "ccn",
    "DRG_Cd": "drg_code",
    "DRG_Desc": "drg_description",
    "Tot_Dschrgs": "total_discharges",
    "Avg_Submtd_Cvrd_Chrg": "avg_covered_charges",
    "Avg_Tot_Pymt_Amt": "avg_total_payments",
    "Avg_Mdcr_Pymt_Amt": "avg_medicare_payments",
}

# Pagination defaults
DEFAULT_PAGE_SIZE = 500
MAX_PAGES = 2000


class CMSInpatientPUFFetcher(BaseFetcher):
    """Fetcher for CMS Inpatient PUF (DRG-level volumes and payments)."""

    SOURCE_NAME = "cms_inpatient_puf"
    BASE_URL = "https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals"

    # API endpoint
    API_ENDPOINT = "https://data.cms.gov/data-api/v1/dataset/medicare-inpatient-hospitals-by-provider-and-service/data"

    def get_latest_url(self) -> str:
        """Return the API endpoint for inpatient PUF data."""
        year = self.params.get("year")
        url = f"{self.API_ENDPOINT}?size={DEFAULT_PAGE_SIZE}&offset=0"
        if year:
            url += f"&filter[year]={year}"
        return url

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch inpatient PUF records via paginated JSON API.

        Keyword Args:
            year: Optional fiscal year filter.
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
            logger.exception("Inpatient PUF fetch failed: %s", exc)
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
        """Page through the CMS Inpatient API.

        Args:
            year: Optional fiscal year filter.
            max_records: Optional record cap.

        Returns:
            List of normalised record dicts.
        """
        records: List[Dict[str, Any]] = []
        offset = resume_offset
        page_size = DEFAULT_PAGE_SIZE

        while True:
            params: Dict[str, Any] = {"size": page_size, "offset": offset}
            if year:
                params["filter[year]"] = year

            logger.debug("Fetching Inpatient PUF page offset=%d", offset)

            self._last_offset = offset
            try:
                data = self.fetch_json(self.API_ENDPOINT, params=params)
            except Exception as exc:
                logger.warning("Inpatient PUF page error at offset %d: %s", offset, exc)
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

        logger.info("Fetched %d Inpatient PUF records", len(records))
        return records

    @staticmethod
    def _normalise(row: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and rename key fields from a raw API row."""
        record: Dict[str, Any] = {}
        for src_field, dest_field in FIELD_MAP.items():
            value = row.get(src_field) or row.get(dest_field)
            record[dest_field] = value
        return record

    def _save_and_hash(
        self,
        records: List[Dict],
        year: Optional[int] = None,
    ) -> Optional[str]:
        """Persist records to a JSON file and return its MD5 hash."""
        import json

        if not records:
            return None

        timestamp = datetime.now().strftime("%Y%m%d")
        year_suffix = f"_fy{year}" if year else ""
        filename = f"cms_inpatient_puf{year_suffix}_{timestamp}.json"
        filepath = self.data_dir / filename

        with open(filepath, "w") as fh:
            json.dump(records, fh)

        return self.calculate_hash(filepath)
