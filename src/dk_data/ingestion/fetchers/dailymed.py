"""DailyMed drug label (SPL) fetcher — full paginated bulk load.

DailyMed (National Library of Medicine) provides FDA-approved drug labeling
(Structured Product Labels) via a public REST API. No credentials required.

API base: https://dailymed.nlm.nih.gov/dailymed/services/v2/

Endpoints used:
  GET /spls.json?pagesize=100&page=N
    → paginated list of all SPLs with setid, title, published date

  Pagination: response includes totalElements; iterate page=1..N until exhausted.

Stores one JSONB record per SPL entry in mol_raw.dailymed (migration 096).
Each record contains the SPL set_id, title, published date, and metadata.

For full label XML content, individual SPLs can be fetched via:
  GET /spls/{set_id}.json
but that would require 100k+ individual requests. The paginated list
provides sufficient metadata for entity matching and enrichment workflows.
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_BASE_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
_PAGE_SIZE = 100
_REQUEST_DELAY = 0.2  # seconds between pages — polite rate limiting


class DailyMedFetcher(BaseFetcher):
    """Fetcher for DailyMed SPL (drug label) metadata via paginated REST API."""

    SOURCE_NAME = "dailymed"
    BASE_URL = _BASE_URL

    def get_latest_url(self) -> str:
        return f"{_BASE_URL}/spls.json?pagesize={_PAGE_SIZE}&page=1"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch all DailyMed SPL metadata via paginated API.

        Keyword Args:
            max_records: Cap total records (useful for testing).
            label_type: Filter by label type ('human', 'animal', 'all'). Default: 'all'.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: Optional[int] = kwargs.get("max_records")
        label_type: str = kwargs.get("label_type", "all")

        try:
            records = self._fetch_paginated(max_records=max_records, label_type=label_type)

            if not records:
                msg = "DailyMed: no SPL records returned — source may be unavailable"
                logger.warning(msg)
                result = {"status": "source_unavailable", "records": [], "record_count": 0, "hash": None, "error": msg}
                self.log_fetch_result(result)
                return result

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
            logger.exception("DailyMed fetch failed: %s", exc)
            result = {"status": "failed", "records": [], "record_count": 0, "hash": None, "error": str(exc)}
            self.log_fetch_result(result)
            return result

    def _fetch_paginated(
        self,
        max_records: Optional[int],
        label_type: str,
    ) -> List[Dict[str, Any]]:
        """Paginate through /spls.json until all records are fetched."""
        all_records: List[Dict[str, Any]] = []
        page = 1
        total_pages: Optional[int] = None

        params: Dict[str, Any] = {"pagesize": _PAGE_SIZE, "page": page}
        if label_type == "human":
            params["type"] = "rxonly,otc,prescription,otc,combination"

        while True:
            params["page"] = page
            logger.info("DailyMed: fetching page %d%s", page, f"/{total_pages}" if total_pages else "")
            resp = self.session.get(f"{_BASE_URL}/spls.json", params=params, timeout=60)
            resp.raise_for_status()

            data = resp.json()
            page_records: List[Dict[str, Any]] = data.get("data", [])

            if not page_records:
                break

            all_records.extend(page_records)

            if total_pages is None:
                meta = data.get("metadata", {})
                total_elements = meta.get("total_elements", 0)
                total_pages = (total_elements + _PAGE_SIZE - 1) // _PAGE_SIZE
                logger.info("DailyMed: total elements=%d, pages=%d", total_elements, total_pages)

            if max_records and len(all_records) >= max_records:
                all_records = all_records[:max_records]
                break

            if total_pages and page >= total_pages:
                break

            page += 1
            time.sleep(_REQUEST_DELAY)

        logger.info("DailyMed: fetched %d SPL records across %d pages", len(all_records), page)
        return all_records
