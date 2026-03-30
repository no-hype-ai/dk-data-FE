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


class FDANDCFetcher(BaseFetcher):
    """Fetcher for FDA National Drug Code directory via OpenFDA API."""

    SOURCE_NAME = "fda_ndc"
    BASE_URL = "https://api.fda.gov"

    def get_latest_url(self) -> str:
        return f"{_API_URL}?limit={_PAGE_SIZE}&skip=0"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch all FDA NDC product records.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: Optional[int] = kwargs.get("max_records")
        # Optionally filter by product type (e.g. HUMAN PRESCRIPTION DRUG)
        product_type: Optional[str] = kwargs.get("product_type")

        try:
            records = self._fetch_paginated(max_records=max_records, product_type=product_type)
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

    def _fetch_paginated(
        self,
        max_records: Optional[int],
        product_type: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Page through OpenFDA /drug/ndc API."""
        all_records: List[Dict[str, Any]] = []
        skip = 0
        total: Optional[int] = None

        search = f'product_type:"{product_type}"' if product_type else None

        while True:
            params: Dict[str, Any] = {"limit": _PAGE_SIZE, "skip": skip}
            if search:
                params["search"] = search

            logger.info("FDA NDC: fetching skip=%d%s", skip, f" (total={total})" if total else "")
            resp = self.session.get(_API_URL, params=params, timeout=60)

            if resp.status_code == 404:
                logger.info("FDA NDC: 404 at skip=%d — end of results", skip)
                break

            resp.raise_for_status()
            data = resp.json()

            if total is None:
                total = data.get("meta", {}).get("results", {}).get("total", 0)
                logger.info("FDA NDC: total=%d products", total)

            page_records = data.get("results", [])
            if not page_records:
                break

            all_records.extend(page_records)

            if max_records and len(all_records) >= max_records:
                all_records = all_records[:max_records]
                break

            skip += _PAGE_SIZE
            if skip > _MAX_SKIP:
                logger.info("FDA NDC: reached FDA skip limit (%d), stopping", _MAX_SKIP)
                break
            if total and skip >= total:
                break

            time.sleep(_REQUEST_DELAY)

        logger.info("FDA NDC: fetched %d product records", len(all_records))
        return all_records
