"""FDA REMS fetcher — Risk Evaluation and Mitigation Strategy programs.

Queries OpenFDA drug/drugsfda endpoint for applications that have REMS
submissions. REMS submissions have submission_type == 'REMS' in their
submissions array.

API: https://api.fda.gov/drug/drugsfda.json
  Public, no authentication, rate limit ~240 requests/minute.
  Search: submissions.submission_type:"REMS"
  Pagination: ?limit=100&skip=N (max skip: 25000)

Stores one JSONB record per NDA/ANDA/BLA application in mol_raw.fda_rems
(migration 126).
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
_MAX_SKIP = 25000
_REMS_SEARCH = 'submissions.submission_type:"REMS"'


class FDARemsFetcher(BaseFetcher):
    """Fetcher for FDA REMS programs via OpenFDA Drugs@FDA API."""

    SOURCE_NAME = "fda_rems"
    BASE_URL = "https://api.fda.gov"

    def get_latest_url(self) -> str:
        return f"{_API_URL}?search={_REMS_SEARCH}&limit={_PAGE_SIZE}&skip=0"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch all FDA REMS application records.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: Optional[int] = kwargs.get("max_records")

        try:
            records = self._fetch_paginated(max_records=max_records)
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
            logger.exception("FDA REMS fetch failed: %s", exc)
            result = {"status": "failed", "records": [], "record_count": 0, "hash": None, "error": str(exc)}
            self.log_fetch_result(result)
            return result

    def _fetch_paginated(self, max_records: Optional[int]) -> List[Dict[str, Any]]:
        """Page through OpenFDA drugsfda API filtering for REMS submissions."""
        all_records: List[Dict[str, Any]] = []
        skip = 0
        total: Optional[int] = None

        while True:
            params = {"search": _REMS_SEARCH, "limit": _PAGE_SIZE, "skip": skip}
            logger.info("FDA REMS: fetching skip=%d%s", skip, f" (total={total})" if total else "")
            resp = self.session.get(_API_URL, params=params, timeout=60)

            if resp.status_code == 404:
                logger.info("FDA REMS: 404 at skip=%d — end of results", skip)
                break

            resp.raise_for_status()
            data = resp.json()

            if total is None:
                total = data.get("meta", {}).get("results", {}).get("total", 0)
                logger.info("FDA REMS: total=%d applications with REMS", total)

            page_records = data.get("results", [])
            if not page_records:
                break

            # Normalize: ensure each record has application_number at top level
            for rec in page_records:
                if "application_number" not in rec:
                    app_nos = rec.get("openfda", {}).get("application_number", [])
                    rec["application_number"] = app_nos[0] if app_nos else None

            all_records.extend(page_records)

            if max_records and len(all_records) >= max_records:
                all_records = all_records[:max_records]
                break

            skip += _PAGE_SIZE
            if skip > _MAX_SKIP:
                logger.info("FDA REMS: reached FDA skip limit (%d), stopping", _MAX_SKIP)
                break
            if total and skip >= total:
                break

            time.sleep(_REQUEST_DELAY)

        logger.info("FDA REMS: fetched %d REMS application records", len(all_records))
        return all_records
