"""FDA Drugs@FDA fetcher — full NDA/ANDA/BLA approval database.

Drugs@FDA contains all FDA-approved drug products including:
  - NDA (New Drug Application), ANDA (abbreviated), BLA (biologics)
  - Approval history, dates, applicants
  - Active ingredients, brand names, dosage forms
  - Research codes via cross-reference to OpenFDA

API: https://api.fda.gov/drug/drugsfda.json
  Public, no authentication, rate limit ~240 requests/minute.
  Pagination: ?limit=100&skip=N (max skip: 25000 per FDA limit).

Full-database strategy:
  1. Page through ?limit=100&skip=0 until records exhausted or skip limit hit.
  2. Total unique application entries: ~30,000 (fits within skip limit).

Stores one JSONB record per application in mol_raw.fda_drugs (migration 096).
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_API_URL = "https://api.fda.gov/drug/drugsfda.json"
_PAGE_SIZE = 100
_REQUEST_DELAY = 0.3   # seconds between pages — stay under 240 req/min
_MAX_SKIP = 25000      # FDA API hard limit on skip parameter

# Partition by application type so each subset stays well under the 25k skip limit.
# Total ~30k applications split: NDA ~10k, ANDA ~17k, BLA ~3k — each fits in one window.
_APPLICATION_TYPE_PARTITIONS = ["NDA", "ANDA", "BLA"]


class FDADrugsFetcher(BaseFetcher):
    """Fetcher for FDA Drugs@FDA approval database via OpenFDA API.

    Uses application-type partitioning (NDA/ANDA/BLA) to work around the FDA API's
    hard skip=25000 limit. Each partition is fetched separately and deduplicated by
    application_number before returning. Covers the full ~30k application database.
    """

    SOURCE_NAME = "fda_drugs"
    BASE_URL = "https://api.fda.gov"

    def get_latest_url(self) -> str:
        return f"{_API_URL}?limit={_PAGE_SIZE}&skip=0"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch all FDA Drugs@FDA records via partitioned + paginated OpenFDA API.

        Keyword Args:
            max_records: Cap total records. Default: all.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: Optional[int] = kwargs.get("max_records")

        try:
            records = self._fetch_all_partitions(max_records=max_records)
            content_hash = hashlib.md5(json.dumps(len(records)).encode()).hexdigest()

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except Exception as exc:
            logger.exception("FDADrugs fetch failed: %s", exc)
            result = {"status": "failed", "records": [], "record_count": 0, "hash": None, "error": str(exc)}
            self.log_fetch_result(result)
            return result

    def _fetch_all_partitions(self, max_records: Optional[int]) -> List[Dict[str, Any]]:
        """Fetch all application types and deduplicate by application_number.

        The FDA API caps skip at 25k. Partitioning by NDA/ANDA/BLA keeps each
        subset well under that limit while covering the full ~30k dataset.
        """
        seen: set = set()
        all_records: List[Dict[str, Any]] = []

        for app_type in _APPLICATION_TYPE_PARTITIONS:
            if max_records and len(all_records) >= max_records:
                break
            search = f'application_number:{app_type}*'
            remaining = None if max_records is None else max_records - len(all_records)
            partition_records = self._fetch_paginated(search=search, max_records=remaining)
            for rec in partition_records:
                app_num = rec.get("application_number", "")
                if app_num not in seen:
                    seen.add(app_num)
                    all_records.append(rec)
            logger.info("FDADrugs: partition=%s → %d records (running total %d)",
                        app_type, len(partition_records), len(all_records))

        logger.info("FDADrugs: %d total unique application records", len(all_records))
        return all_records

    def _fetch_paginated(self, search: Optional[str], max_records: Optional[int]) -> List[Dict[str, Any]]:
        """Page through the FDA Drugs@FDA API for a single search partition."""
        all_records: List[Dict[str, Any]] = []
        skip = 0
        total: Optional[int] = None

        while True:
            params: Dict[str, Any] = {"limit": _PAGE_SIZE, "skip": skip}
            if search:
                params["search"] = search
            logger.debug("FDADrugs: skip=%d search=%s", skip, search)
            resp = self.session.get(_API_URL, params=params, timeout=60)

            if resp.status_code == 404:
                break

            resp.raise_for_status()
            data = resp.json()

            if total is None:
                total = data.get("meta", {}).get("results", {}).get("total", 0)
                logger.info("FDADrugs[%s]: total=%d", search, total)

            page_records = data.get("results", [])
            if not page_records:
                break

            all_records.extend(page_records)

            if max_records and len(all_records) >= max_records:
                all_records = all_records[:max_records]
                break

            skip += _PAGE_SIZE
            if skip > _MAX_SKIP:
                logger.warning("FDADrugs[%s]: reached skip limit with %d records — partition may be incomplete",
                               search, len(all_records))
                break
            if total and skip >= total:
                break

            time.sleep(_REQUEST_DELAY)

        return all_records
