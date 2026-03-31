"""FDA Purple Book fetcher — licensed biological products (BLA applications).

Fetches Biologics License Application (BLA) records from the FDA
Drugs@FDA openFDA API, filtered for biologic products. The Purple Book
is the authoritative reference for FDA-approved biological drugs.

API: https://api.fda.gov/drug/drugsfda.json
  Public, no authentication required.
  Filtered by: products.drug_type:BLA
  Total: ~5,000 BLA application records.
  Pagination: ?limit=100&skip=N (FDA skip limit: 25,000).
  Dedup by: application_number.

Stores one JSONB record per BLA application in mol_raw.purple_book.
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
_REQUEST_DELAY = 0.3
_FDA_SKIP_LIMIT = 25_000
_DEFAULT_MAX_RECORDS = 10_000


class PurpleBookFetcher(BaseFetcher):
    """Fetcher for FDA Purple Book (BLA) records via openFDA Drugs@FDA API.

    Pages through the /drug/drugsfda endpoint filtered for BLA applications.
    Each record is an application dict keyed by application_number.
    Deduplication at load time uses an expression index on
    response_body->>'application_number'.
    """

    SOURCE_NAME = "purple_book"
    BASE_URL = "https://api.fda.gov"

    def get_latest_url(self) -> str:
        return f"{_API_URL}?search=products.drug_type:BLA&limit={_PAGE_SIZE}&skip=0"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch FDA Purple Book BLA records via openFDA Drugs@FDA API.

        Keyword Args:
            max_records: Cap total records. Default: 10,000.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: int = min(
            int(kwargs.get("max_records", _DEFAULT_MAX_RECORDS)),
            _FDA_SKIP_LIMIT,
        )

        try:
            records = self._fetch_paginated(max_records=max_records)
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
            logger.exception("Purple Book fetch failed: %s", exc)
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
        """Page through the FDA Drugs@FDA API for BLA applications."""
        all_records: List[Dict[str, Any]] = []
        skip = 0
        total: Optional[int] = None

        while len(all_records) < max_records:
            remaining = max_records - len(all_records)
            limit = min(_PAGE_SIZE, remaining)

            params: Dict[str, Any] = {
                "search": "products.drug_type:BLA",
                "limit": limit,
                "skip": skip,
            }

            logger.debug("Purple Book: skip=%d limit=%d", skip, limit)

            try:
                resp = self.session.get(_API_URL, params=params, timeout=60)
                if resp.status_code == 404:
                    break
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning(
                    "Purple Book request failed at skip=%d: %s", skip, exc
                )
                break

            if total is None:
                total = (
                    data.get("meta", {}).get("results", {}).get("total", 0)
                )
                logger.info("Purple Book: total_count=%d", total)

            results = data.get("results", [])
            if not results:
                break

            all_records.extend(results)
            logger.info(
                "Purple Book: skip=%d fetched %d records (running total=%d)",
                skip, len(results), len(all_records),
            )

            if len(results) < limit:
                break

            skip += limit
            if skip >= _FDA_SKIP_LIMIT:
                logger.warning(
                    "Purple Book: hit FDA skip limit (%d) with %d records",
                    _FDA_SKIP_LIMIT, len(all_records),
                )
                break
            if total and skip >= total:
                break

            time.sleep(_REQUEST_DELAY)

        logger.info("Purple Book: %d total BLA records fetched", len(all_records))
        return all_records
