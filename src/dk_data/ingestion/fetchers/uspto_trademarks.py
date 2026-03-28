"""USPTO TSDR Trademark Data Fetcher.

Feature: 014-uspto-euipo-model-datasource
Task: T011 — USPTO TSDR trademark case status data

Fetches pharmaceutical trademark data from the USPTO Trademark Status
and Document Retrieval (TSDR) API using API key authentication.

Source: https://tsdrapi.uspto.gov
Auth: API key via USPTO_TSDR_API_KEY env var
Note: TSDR is lookup-only (no search by Nice Class). Requires serial numbers.
"""

import hashlib
import logging
import os
import time
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Rate limits: 60 req/min standard, 4 req/min batch
REQUEST_DELAY = 1.0  # seconds between standard requests
BATCH_REQUEST_DELAY = 15.0  # seconds between batch requests

# Batch endpoint max serial numbers per request
BATCH_SIZE = 50


class USPTOTrademarksFetcher(BaseFetcher):
    """Fetcher for USPTO TSDR trademark case status data."""

    SOURCE_NAME = "uspto_trademarks"
    BASE_URL = "https://tsdrapi.uspto.gov"

    def __init__(self, data_dir: Optional[str] = None):
        """Initialize the USPTO Trademarks fetcher.

        Reads USPTO_TSDR_API_KEY from the environment.
        """
        super().__init__(data_dir)

        self.api_key: Optional[str] = os.environ.get("USPTO_TSDR_API_KEY")
        if self.api_key:
            self.session.headers.update({"USPTO-API-KEY": self.api_key})
        else:
            logger.warning("USPTO_TSDR_API_KEY not set; TSDR API calls will fail")

    def get_latest_url(self) -> str:
        """Return the TSDR API base URL."""
        return self.BASE_URL

    def fetch(
        self,
        serial_numbers: Optional[List[str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Fetch trademark data for given serial numbers.

        Args:
            serial_numbers: List of serial numbers to look up.
                           If None, attempts to read from raw table for refresh.

        Returns:
            Dict with status, records, record_count, hash.
        """
        try:
            if not serial_numbers:
                serial_numbers = self._load_serial_numbers_from_db()

            if not serial_numbers:
                logger.warning(
                    "No serial numbers provided and none found in DB. "
                    "TSDR API is lookup-only — cannot search by Nice Class."
                )
                return {
                    "status": "success",
                    "records": [],
                    "record_count": 0,
                    "hash": None,
                }

            logger.info(
                "Fetching USPTO trademark data for %d serial numbers",
                len(serial_numbers),
            )

            all_records: List[Dict[str, Any]] = []
            seen_sns: set = set()
            batch_errors: int = 0
            batches_attempted: int = 0

            # Process in batches using multi-case endpoint
            for i in range(0, len(serial_numbers), BATCH_SIZE):
                batch = serial_numbers[i : i + BATCH_SIZE]
                batches_attempted += 1
                records = self._fetch_batch(batch)

                if not records:
                    batch_errors += 1

                for rec in records:
                    sn = rec.get("serial_number")
                    if sn and sn not in seen_sns:
                        seen_sns.add(sn)
                        all_records.append(rec)

                if i + BATCH_SIZE < len(serial_numbers):
                    time.sleep(BATCH_REQUEST_DELAY)

            content_hash = hashlib.md5(
                str(sorted(seen_sns)).encode()
            ).hexdigest()

            # Determine status: failed if all batches errored, partial if some
            if not all_records and batch_errors == batches_attempted and batches_attempted > 0:
                status = "failed"
            elif batch_errors > 0:
                status = "partial"
            else:
                status = "success"

            result = {
                "status": status,
                "records": all_records,
                "record_count": len(all_records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": status, "records": len(all_records)})
            return result

        except Exception as e:
            logger.exception("Failed to fetch USPTO trademark data: %s", e)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(e),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_batch(self, serial_numbers: List[str]) -> List[Dict[str, Any]]:
        """Fetch a batch of trademarks using the multi-case endpoint.

        GET /ts/cd/caseMultiStatus/sn?ids={comma-separated}
        """
        records: List[Dict[str, Any]] = []

        ids_param = ",".join(serial_numbers)
        url = f"{self.BASE_URL}/ts/cd/caseMultiStatus/sn"

        try:
            response = self.session.get(
                url,
                params={"ids": ids_param},
                timeout=60,
            )

            if response.status_code == 401:
                logger.error(
                    "USPTO TSDR API authentication failed (401). "
                    "Check USPTO_TSDR_API_KEY."
                )
                return records

            response.raise_for_status()

            data = response.json()

            # TSDR batch response is a list of trademark case objects
            cases = data if isinstance(data, list) else data.get("trademarks", [])

            for raw_case in cases:
                normalized = self._normalize_trademark(raw_case)
                if normalized:
                    records.append(normalized)

        except Exception as e:
            logger.warning(
                "TSDR batch request failed for %d serial numbers: %s",
                len(serial_numbers),
                e,
            )

        return records

    @staticmethod
    def _normalize_trademark(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize TSDR API response to flat record.

        Maps Swagger Trademark object fields to raw table columns:
        - serialNumber -> serial_number
        - markElement -> mark_element
        - statusStr -> status
        - statusDate -> status_date
        - filingDate -> filing_date
        - usRegistrationNumber -> registration_number
        - gsList[].internationalClasses -> nice_classes
        - parties.currentOwners[0].name -> owner_name
        """
        serial_number = raw.get("serialNumber") or raw.get("serial_number")
        if not serial_number:
            return None

        # Extract Nice classes from goods/services list
        nice_classes: List[int] = []
        gs_list = raw.get("gsList") or raw.get("goodsAndServices") or []
        if isinstance(gs_list, list):
            for gs in gs_list:
                if isinstance(gs, dict):
                    ic = gs.get("internationalClasses") or gs.get("niceClasses") or []
                    if isinstance(ic, list):
                        nice_classes.extend(int(c) for c in ic if str(c).isdigit())
                    elif isinstance(ic, (int, str)) and str(ic).isdigit():
                        nice_classes.append(int(ic))

        # Extract owner info
        owner_name = None
        owner_entity_type = None
        parties = raw.get("parties") or {}
        owners = parties.get("currentOwners") or parties.get("owners") or []
        if isinstance(owners, list) and owners:
            first_owner = owners[0] if isinstance(owners[0], dict) else {}
            owner_name = first_owner.get("name") or first_owner.get("entityName")
            owner_entity_type = first_owner.get("entityType")

        return {
            "serial_number": str(serial_number),
            "mark_element": raw.get("markElement") or raw.get("mark_element"),
            "mark_type": raw.get("markType") or raw.get("mark_type"),
            "status": raw.get("statusStr") or raw.get("status"),
            "status_code": raw.get("statusCode") or raw.get("status_code"),
            "status_date": raw.get("statusDate") or raw.get("status_date"),
            "filing_date": raw.get("filingDate") or raw.get("filing_date"),
            "registration_number": (
                raw.get("usRegistrationNumber")
                or raw.get("registrationNumber")
                or raw.get("registration_number")
            ),
            "registration_date": (
                raw.get("registrationDate") or raw.get("registration_date")
            ),
            "nice_classes": sorted(set(nice_classes)) if nice_classes else None,
            "us_classes": raw.get("usClasses") or raw.get("us_classes"),
            "owner_name": owner_name,
            "owner_entity_type": owner_entity_type,
            "goods_and_services": raw.get("goodsAndServicesText") or raw.get("goods_and_services"),
            "description_of_mark": raw.get("descriptionOfMark") or raw.get("description_of_mark"),
        }

    def _load_serial_numbers_from_db(self) -> List[str]:
        """Load existing serial numbers from raw.uspto_trademarks for refresh."""
        try:
            from ..utils.database import get_connection

            serial_numbers: List[str] = []
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT serial_number FROM mol_raw.uspto_trademarks ORDER BY _loaded_at ASC"
                    )
                    for row in cur.fetchall():
                        serial_numbers.append(row[0])

            logger.info(
                "Loaded %d serial numbers from mol_raw.uspto_trademarks for refresh",
                len(serial_numbers),
            )
            return serial_numbers

        except Exception as e:
            logger.warning("Could not load serial numbers from DB: %s", e)
            return []
