"""CMS Open Payments Data Fetcher.

Fetches physician payment data from the Open Payments programme covering
General payments, Research payments, and Ownership/investment interests.
Uses the Open Payments Data API (Datastore SQL endpoint).

Source: https://openpaymentsdata.cms.gov
"""

import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Dataset UUIDs per payment type and year (DKAN, post-migration).
# Old Socrata IDs (yypq-mgs4, etc.) are retired.
PAYMENT_TYPE_DATASETS_BY_YEAR: Dict[str, Dict[str, str]] = {
    "general": {
        "2024": "e6b17c6a-2534-4207-a4a1-6746a14911ff",
        "2023": "fb3a65aa-c901-4a38-a813-b04b00dfa2a9",
        "2022": "df01c2f8-dc1f-4e79-96cb-8208beaf143c",
    },
    "research": {
        "2024": "2f15cb85-8887-4dcc-a318-1f8ec1d815b3",
        "2023": "ec9521bf-9d97-4603-814c-f4132d34bc4f",
        "2022": "fdc3c773-018a-412c-8a81-d7b8a13a037b",
    },
    "ownership": {
        "2024": "9ac4f7f8-b6e4-4d80-8410-4aba7e71dd02",
        "2023": "ac0bc85c-02e3-45d9-89e8-2ff43da85df7",
        "2022": "37792388-800f-427a-9e02-b11601454eeb",
    },
}
# Default year when none specified
DEFAULT_PAYMENT_YEAR = "2024"

# Backwards-compatible flat map (uses default year)
PAYMENT_TYPE_DATASETS: Dict[str, str] = {
    pt: years[DEFAULT_PAYMENT_YEAR]
    for pt, years in PAYMENT_TYPE_DATASETS_BY_YEAR.items()
}

# Key fields per payment type
GENERAL_FIELDS = [
    "covered_recipient_npi",
    "applicable_manufacturer_or_applicable_gpo_making_payment_name",
    "total_amount_of_payment_usdollars",
    "date_of_payment",
    "nature_of_payment_or_transfer_of_value",
    "form_of_payment_or_transfer_of_value",
]

RESEARCH_FIELDS = [
    "covered_recipient_npi",
    "applicable_manufacturer_or_applicable_gpo_making_payment_name",
    "total_amount_of_payment_usdollars",
    "date_of_payment",
    "form_of_payment_or_transfer_of_value",
    "name_of_study",
]

OWNERSHIP_FIELDS = [
    "physician_profile_id",
    "applicable_manufacturer_or_applicable_gpo_making_payment_name",
    "total_amount_invested_usdollars",
    "interest_held_by_physician_or_an_immediate_family_member",
    "value_of_interest",
]

FIELDS_BY_TYPE: Dict[str, List[str]] = {
    "general": GENERAL_FIELDS,
    "research": RESEARCH_FIELDS,
    "ownership": OWNERSHIP_FIELDS,
}

# Pagination defaults
DEFAULT_PAGE_SIZE = 500
MAX_PAGES = 2000


class CMSOpenPaymentsFetcher(BaseFetcher):
    """Fetcher for CMS Open Payments data (General, Research, Ownership)."""

    SOURCE_NAME = "cms_open_payments"
    BASE_URL = "https://openpaymentsdata.cms.gov/api/1/datastore/query"

    def get_latest_url(self) -> str:
        """Return the datastore query URL for the configured payment type."""
        payment_type = self.params.get("payment_type", "general")
        year = str(self.params.get("year", DEFAULT_PAYMENT_YEAR))
        years_map = PAYMENT_TYPE_DATASETS_BY_YEAR.get(payment_type, PAYMENT_TYPE_DATASETS_BY_YEAR["general"])
        dataset_id = years_map.get(year, years_map[DEFAULT_PAYMENT_YEAR])
        return f"{self.BASE_URL}/{dataset_id}/0"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch Open Payments records for one or all payment types.

        When no ``payment_type`` is specified, fetches general, research, and
        ownership in sequence and returns all records combined.

        Keyword Args:
            payment_type: One of general/research/ownership. Omit for all three.
            year: Optional year filter.
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        payment_type = kwargs.get("payment_type") or self.params.get("payment_type")
        year = kwargs.get("year") or self.params.get("year")
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        # When no specific type requested, loop through all three
        types_to_fetch = [payment_type] if payment_type else list(PAYMENT_TYPE_DATASETS.keys())

        for pt in types_to_fetch:
            if pt not in PAYMENT_TYPE_DATASETS:
                result: Dict[str, Any] = {
                    "status": "failed",
                    "records": [],
                    "hash": None,
                    "error": f"Unknown payment_type '{pt}'. Valid: {list(PAYMENT_TYPE_DATASETS.keys())}",
                }
                self.log_fetch_result(result)
                return result

        try:
            all_records: List[Dict[str, Any]] = []
            year_str = str(year) if year else DEFAULT_PAYMENT_YEAR

            for pt in types_to_fetch:
                years_map = PAYMENT_TYPE_DATASETS_BY_YEAR.get(pt, PAYMENT_TYPE_DATASETS_BY_YEAR["general"])
                dataset_id = years_map.get(year_str, years_map[DEFAULT_PAYMENT_YEAR])
                records = self._fetch_paginated(
                    dataset_id=dataset_id,
                    payment_type=pt,
                    year=year,
                    max_records=max_records,
                    resume_offset=kwargs.get('resume_offset', 0),
                )
                all_records.extend(records)
                logger.info("Fetched %d records for payment_type=%s", len(records), pt)

            file_hash = self._save_and_hash(all_records, "_".join(types_to_fetch), year)

            result = {
                "status": "success",
                "records": all_records,
                "hash": file_hash,
            }
            self.log_fetch_result(result)
            return result

        except Exception as exc:
            logger.exception("Open Payments fetch failed: %s", exc)
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
        dataset_id: str,
        payment_type: str,
        year: Optional[int] = None,
        max_records: Optional[int] = None,
        resume_offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Page through the CMS datastore SQL endpoint.

        Args:
            dataset_id: The dataset distribution ID.
            payment_type: One of general / research / ownership.
            year: Optional year filter.
            max_records: Optional record cap.

        Returns:
            List of normalised record dicts.
        """
        records: List[Dict[str, Any]] = []
        offset = resume_offset
        page_size = DEFAULT_PAGE_SIZE

        while True:
            # DKAN datastore query endpoint with limit/offset pagination
            url = f"{self.BASE_URL}/{dataset_id}/0"
            params: Dict[str, Any] = {"limit": page_size, "offset": offset}

            logger.debug("Fetching Open Payments page offset=%d", offset)

            self._last_offset = offset
            try:
                response = self.session.get(url, params=params, timeout=120)
                response.raise_for_status()
                data = response.json()
            except Exception as exc:
                logger.warning("Open Payments page fetch error at offset %d: %s", offset, exc)
                break

            page_records = data.get("results", []) if isinstance(data, dict) else data

            if not page_records:
                break

            for row in page_records:
                record = self._normalise(row, payment_type)
                if record:
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

        logger.info("Fetched %d Open Payments (%s) records", len(records), payment_type)
        return records

    def _normalise(self, row: Dict[str, Any], payment_type: str) -> Optional[Dict[str, Any]]:
        """Map CMS Open Payments API field names to loader-expected names.

        The loader (CmsOpenPaymentRecord) expects:
            record_id, payment_type, covered_recipient_npi, manufacturer_name,
            total_amount_usd, date_of_payment, nature_of_payment, form_of_payment

        The API returns raw field names like:
            applicable_manufacturer_or_applicable_gpo_making_payment_name,
            total_amount_of_payment_usdollars, etc.
        """
        npi = row.get("covered_recipient_npi") or row.get("Covered_Recipient_NPI") or ""
        manufacturer = (
            row.get("applicable_manufacturer_or_applicable_gpo_making_payment_name")
            or row.get("Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_Name")
            or ""
        )
        amount = (
            row.get("total_amount_of_payment_usdollars")
            or row.get("Total_Amount_of_Payment_USDollars")
            or row.get("total_amount_invested_usdollars")
            or row.get("Total_Amount_Invested_USDollars")
        )
        date = row.get("date_of_payment") or row.get("Date_of_Payment") or ""
        nature = (
            row.get("nature_of_payment_or_transfer_of_value")
            or row.get("Nature_of_Payment_or_Transfer_of_Value")
        )
        form = (
            row.get("form_of_payment_or_transfer_of_value")
            or row.get("Form_of_Payment_or_Transfer_of_Value")
        )

        # Generate a deterministic record_id from key fields
        hash_input = f"{npi}|{manufacturer}|{amount}|{date}".encode("utf-8")
        record_id = hashlib.sha256(hash_input).hexdigest()[:32]

        pt = self.params.get("payment_type", payment_type or "general")

        try:
            amount_float = float(amount) if amount is not None else None
        except (ValueError, TypeError):
            amount_float = None

        return {
            "record_id": record_id,
            "payment_type": pt,
            "covered_recipient_npi": npi or None,
            "manufacturer_name": manufacturer or None,
            "total_amount_usd": amount_float,
            "date_of_payment": date or None,
            "nature_of_payment": nature,
            "form_of_payment": form,
        }

    @staticmethod
    def _build_query(
        dataset_id: str,
        offset: int = 0,
        limit: int = DEFAULT_PAGE_SIZE,
        year: Optional[int] = None,
    ) -> str:
        """Build a CMS datastore SQL query string.

        Args:
            dataset_id: Dataset distribution identifier.
            offset: Row offset for pagination.
            limit: Page size.
            year: Optional year filter.

        Returns:
            Encoded SQL query string for the CMS API.
        """
        where_clause = ""
        if year:
            where_clause = f"[WHERE program_year = '{year}']"

        return f"[SELECT * FROM {dataset_id}]{where_clause}[LIMIT {limit} OFFSET {offset}]"

    def _save_and_hash(
        self,
        records: List[Dict],
        payment_type: str,
        year: Optional[int] = None,
    ) -> Optional[str]:
        """Persist records to a JSON file and return its MD5 hash."""
        import json

        if not records:
            return None

        timestamp = datetime.now().strftime("%Y%m%d")
        year_suffix = f"_{year}" if year else ""
        filename = f"cms_open_payments_{payment_type}{year_suffix}_{timestamp}.json"
        filepath = self.data_dir / filename

        with open(filepath, "w") as fh:
            json.dump(records, fh)

        return self.calculate_hash(filepath)
