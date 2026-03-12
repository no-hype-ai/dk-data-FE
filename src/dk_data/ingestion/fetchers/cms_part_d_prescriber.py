"""CMS Medicare Part D Prescriber Data Fetcher.

Fetches prescriber-level Part D utilisation data from the CMS data.gov
API.  The dataset provides information on prescription drugs prescribed
by individual physicians and other health care providers under the
Medicare Part D program.

Source: https://data.cms.gov/provider-summary-by-type-of-service/medicare-part-d-prescribers
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Normalised output field names
KEY_FIELDS = [
    "npi",
    "prscrbr_last_org_name",
    "prscrbr_first_name",
    "prscrbr_city",
    "prscrbr_state_abrvtn",
    "prscrbr_type",
    "brnd_name",
    "gnrc_name",
    "tot_clms",
    "tot_30day_fill_cnt",
    "tot_drug_cst",
    "tot_benes",
]

# CMS API pagination defaults
DEFAULT_PAGE_SIZE = 500
MAX_PAGES = 2000  # Safety limit (~1M records)


class CMSPartDPrescriberFetcher(BaseFetcher):
    """Fetcher for CMS Medicare Part D Prescriber data."""

    SOURCE_NAME = "cms_part_d_prescriber"
    BASE_URL = "https://data.cms.gov/provider-summary-by-type-of-service/medicare-part-d-prescribers"

    # CMS data.gov API endpoint — UUID-based (slug endpoints retired)
    # UUID may change with each annual release; latest known = 2023 data
    DATASET_UUIDS = {
        "2023": "9552739e-3d05-4c1b-8eff-ecabf391e2e5",
        "2022": "b101b457-ffa4-49bb-8fd9-27c1266086e2",
        "2021": "f68114ed-f854-4ffc-9c6e-ed78b5e2f8d0",
        "2020": "7795fe20-e80e-435a-a9ed-d2d65e05feeb",
    }
    DEFAULT_UUID = "9552739e-3d05-4c1b-8eff-ecabf391e2e5"  # 2023

    def get_latest_url(self) -> str:
        """Get the API URL for Part D prescriber data."""
        year = self.params.get("year")
        uuid = self.DATASET_UUIDS.get(str(year), self.DEFAULT_UUID) if year else self.DEFAULT_UUID
        return f"https://data.cms.gov/data-api/v1/dataset/{uuid}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch Part D prescriber records from the CMS API.

        Paginates through the JSON API collecting all records (or up to
        the safety limit).

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

            # Compute a hash over the serialised result for change detection
            file_hash = self._save_and_hash(records, year)

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "hash": file_hash,
            }
            self.log_fetch_result(result)
            return result

        except Exception as exc:
            logger.exception("Part D prescriber fetch failed: %s", exc)
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
                params["filter[Prscrbr_Type_Src]"] = ""  # placeholder to keep params dict
                # CMS uses query-string year filtering
                params["year"] = year

            logger.debug(
                "Fetching Part D prescriber page offset=%d size=%d",
                offset,
                page_size,
            )

            url = self.get_latest_url()
            self._last_offset = offset
            data = self.fetch_json(url, params=params)

            # The CMS data API returns a list directly
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

        logger.info("Fetched %d Part D prescriber records", len(records))
        return records

    @staticmethod
    def _normalise(row: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and lowercase key fields from a raw API row."""
        record: Dict[str, Any] = {}
        for field in KEY_FIELDS:
            # CMS API returns fields in various casings; try exact then upper
            value = row.get(field) or row.get(field.upper()) or row.get(field.lower())
            record[field] = value
        return record

    def _save_and_hash(self, records: List[Dict], year: Optional[int] = None) -> Optional[str]:
        """Persist records to a JSON file and return its hash."""
        import json

        if not records:
            return None

        timestamp = datetime.now().strftime("%Y%m%d")
        year_suffix = f"_{year}" if year else ""
        filename = f"cms_part_d_prescriber{year_suffix}_{timestamp}.json"
        filepath = self.data_dir / filename

        with open(filepath, "w") as fh:
            json.dump(records, fh)

        return self.calculate_hash(filepath)
