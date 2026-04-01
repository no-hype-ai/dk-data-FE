"""FDA NDC fetcher — National Drug Code directory.

OpenFDA /drug/ndc endpoint provides product-level NDC codes with
generic_name, brand_name, labeler, dosage form, route, active ingredients,
and package-level NDCs.

API: https://api.fda.gov/drug/ndc.json
  Public, no authentication, rate limit ~240 requests/minute.
  Total records: ~100,000 products.
  Pagination: ?limit=1000&skip=N (max skip: 25000 per FDA limit).

Stores one JSONB record per NDC product in mol_raw.fda_ndc (migration 126).
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_API_URL = "https://api.fda.gov/drug/ndc.json"
_PAGE_SIZE = 1000
_REQUEST_DELAY = 0.3
_MAX_SKIP = 25000

# Alphabetic partitions on generic_name first character.
# FDA API caps skip=25000. ~100k NDC products split across 26 letter buckets
# gives ~4k per bucket on average — well under the limit.
# '[0-9]' catches numeric-starting names; '[^a-z0-9]' catches symbols/blanks.
_ALPHA_PARTITIONS = list("abcdefghijklmnopqrstuvwxyz") + ["[0-9]", "[^a-z0-9]"]


class FDANDCFetcher(BaseFetcher):
    """Fetcher for FDA National Drug Code directory via OpenFDA API.

    Uses alphabetic partitioning on generic_name to work around the FDA API's
    hard skip=25000 limit. Each of the 28 letter/number partitions is fetched
    separately, deduplicated by product_ndc, covering the full ~100k product set.
    """

    SOURCE_NAME = "fda_ndc"
    BASE_URL = "https://api.fda.gov"

    def get_latest_url(self) -> str:
        return f"{_API_URL}?limit={_PAGE_SIZE}&skip=0"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch all FDA NDC product records via partitioned + paginated OpenFDA API.

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
            logger.exception("FDA NDC fetch failed: %s", exc)
            result = {"status": "failed", "records": [], "record_count": 0, "hash": None, "error": str(exc)}
            self.log_fetch_result(result)
            return result

    def _fetch_all_partitions(self, max_records: Optional[int]) -> List[Dict[str, Any]]:
        """Fetch all 28 alphabetic partitions and deduplicate by product_ndc."""
        seen: set = set()
        all_records: List[Dict[str, Any]] = []

        for letter in _ALPHA_PARTITIONS:
            if max_records and len(all_records) >= max_records:
                break
            search = f"generic_name:{letter}*"
            remaining = None if max_records is None else max_records - len(all_records)
            partition_records = self._fetch_paginated(search=search, max_records=remaining)
            added = 0
            for rec in partition_records:
                ndc = rec.get("product_ndc", "")
                if ndc not in seen:
                    seen.add(ndc)
                    all_records.append(rec)
                    added += 1
            logger.info("FDA NDC: partition=%r → %d new records (running total %d)",
                        letter, added, len(all_records))

        logger.info("FDA NDC: %d total unique NDC products", len(all_records))
        return all_records

    def _fetch_paginated(self, search: Optional[str], max_records: Optional[int]) -> List[Dict[str, Any]]:
        """Page through OpenFDA /drug/ndc API for a single search partition."""
        all_records: List[Dict[str, Any]] = []
        skip = 0
        total: Optional[int] = None

        while True:
            params: Dict[str, Any] = {"limit": _PAGE_SIZE, "skip": skip}
            if search:
                params["search"] = search

            logger.debug("FDA NDC: skip=%d search=%s", skip, search)
            resp = self.session.get(_API_URL, params=params, timeout=60)

            if resp.status_code == 404:
                break

            resp.raise_for_status()
            data = resp.json()

            if total is None:
                total = data.get("meta", {}).get("results", {}).get("total", 0)
                logger.info("FDA NDC[%s]: total=%d", search, total)

            page_records = data.get("results", [])
            if not page_records:
                break

            all_records.extend(page_records)

            if max_records and len(all_records) >= max_records:
                all_records = all_records[:max_records]
                break

            skip += _PAGE_SIZE
            if skip > _MAX_SKIP:
                logger.warning("FDA NDC[%s]: hit skip limit with %d records — partition may need sub-splitting",
                               search, len(all_records))
                break
            if total and skip >= total:
                break

            time.sleep(_REQUEST_DELAY)

        return all_records
