"""NPI Registry fetcher — CMS National Provider Identifier registry.

Fetches provider records from the NPPES NPI Registry public API.
Each record contains provider identifying information, taxonomy codes,
addresses, and license data for individual and organizational providers.

API: https://npiregistry.cms.hhs.gov/api/?version=2.1
  Public, no authentication required.
  Pagination: skip offset, max limit=200 per request.
  Total: ~7M active NPIs.
  Dedup by: number (NPI number, 10-digit string).

Stores one JSONB record per NPI in mol_raw.npi_registry.
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_API_URL = "https://npiregistry.cms.hhs.gov/api/"
_PAGE_SIZE = 200
_REQUEST_DELAY = 0.2
_MAX_SKIP = 1_000_000


class NPIRegistryFetcher(BaseFetcher):
    """Fetcher for CMS NPI Registry provider records.

    Paginates through all active NPIs using skip/limit. Each record is a
    provider dict keyed by ``number`` (the 10-digit NPI). Deduplication at
    load time uses an expression index on response_body->>'number'.
    """

    SOURCE_NAME = "npi_registry"
    BASE_URL = "https://npiregistry.cms.hhs.gov/api"

    def get_latest_url(self) -> str:
        return f"{_API_URL}?version=2.1&limit={_PAGE_SIZE}&skip=0"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch NPI Registry provider records via paginated API.

        Keyword Args:
            max_records: Cap total records. Default: None (all, capped at 1M).

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: Optional[int] = kwargs.get("max_records")
        effective_max = min(max_records, _MAX_SKIP) if max_records else _MAX_SKIP

        try:
            records = self._fetch_paginated(max_records=effective_max)
            content_hash = hashlib.md5(
                json.dumps(len(records)).encode()
            ).hexdigest()

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except Exception as exc:
            logger.exception("NPI Registry fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_paginated(self, max_records: int) -> List[Dict[str, Any]]:
        """Page through the NPI Registry API using skip/limit pagination."""
        all_records: List[Dict[str, Any]] = []
        skip = 0

        while len(all_records) < max_records:
            remaining = max_records - len(all_records)
            limit = min(_PAGE_SIZE, remaining)

            params: Dict[str, Any] = {
                "version": "2.1",
                "limit": limit,
                "skip": skip,
            }

            logger.debug("NPI Registry: skip=%d limit=%d", skip, limit)

            try:
                resp = self.session.get(_API_URL, params=params, timeout=60)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning(
                    "NPI Registry request failed at skip=%d: %s", skip, exc
                )
                break

            results = data.get("results", [])
            if not results:
                logger.info("NPI Registry: empty page at skip=%d — done", skip)
                break

            all_records.extend(results)
            logger.info(
                "NPI Registry: skip=%d fetched %d records (running total=%d)",
                skip, len(results), len(all_records),
            )

            if len(results) < limit:
                break

            skip += limit
            if skip >= _MAX_SKIP:
                logger.warning(
                    "NPI Registry: reached skip cap (%d) with %d records",
                    _MAX_SKIP, len(all_records),
                )
                break

            time.sleep(_REQUEST_DELAY)

        logger.info("NPI Registry: %d total providers fetched", len(all_records))
        return all_records
