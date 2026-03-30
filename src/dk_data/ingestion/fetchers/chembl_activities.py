"""ChEMBL Activities fetcher — bioactivity assay measurements.

ChEMBL /api/data/activity endpoint provides IC50, Ki, EC50 and other
activity measurements linking compounds (molecule_chembl_id) to assays
and biological targets (target_chembl_id).

API: https://www.ebi.ac.uk/chembl/api/data/activity.json
  Public, no authentication, rate limit ~1 req/sec recommended.
  Pagination: ?limit=1000&offset=N

Full-database strategy:
  Page through all activities. ChEMBL has ~20M activity records; initial
  load is large. Subsequent runs use days_back to limit to recent records
  by filtering on document_year or offset-based delta.

Stores page blobs in mol_raw.chembl_activities (migration 126).
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_API_URL = "https://www.ebi.ac.uk/chembl/api/data/activity.json"
_PAGE_SIZE = 1000
_REQUEST_DELAY = 1.0   # 1 req/sec — ChEMBL fair-use recommendation
_MAX_RECORDS_DEFAULT = 500_000  # Safety cap for first run; remove for full load


class ChEMBLActivitiesFetcher(BaseFetcher):
    """Fetcher for ChEMBL bioactivity measurements via REST API."""

    SOURCE_NAME = "chembl_activities"
    BASE_URL = "https://www.ebi.ac.uk"

    def get_latest_url(self) -> str:
        return f"{_API_URL}?limit={_PAGE_SIZE}&offset=0"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch ChEMBL activity records via paginated REST API.

        Keyword Args:
            max_records: Cap total records (default 500k for safety).
            pchembl_min: Minimum pChEMBL value filter (e.g. 5.0 for sub-10µM).

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: Optional[int] = kwargs.get("max_records", _MAX_RECORDS_DEFAULT)
        pchembl_min: Optional[float] = kwargs.get("pchembl_min")

        try:
            records = self._fetch_paginated(max_records=max_records, pchembl_min=pchembl_min)
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
            logger.exception("ChEMBL Activities fetch failed: %s", exc)
            result = {"status": "failed", "records": [], "record_count": 0, "hash": None, "error": str(exc)}
            self.log_fetch_result(result)
            return result

    def _fetch_paginated(
        self,
        max_records: Optional[int],
        pchembl_min: Optional[float],
    ) -> List[Dict[str, Any]]:
        """Page through ChEMBL activity API, wrapping each page as a blob."""
        all_blobs: List[Dict[str, Any]] = []
        offset = 0
        page_num = 0
        total: Optional[int] = None
        total_activity_count = 0

        while True:
            params: Dict[str, Any] = {"limit": _PAGE_SIZE, "offset": offset, "format": "json"}
            if pchembl_min is not None:
                params["pchembl_value__gte"] = pchembl_min

            logger.info(
                "ChEMBL Activities: page %d, offset=%d%s",
                page_num,
                offset,
                f" (total={total})" if total else "",
            )
            resp = self.session.get(_API_URL, params=params, timeout=90)

            if resp.status_code == 404:
                logger.info("ChEMBL Activities: 404 at offset=%d — end of results", offset)
                break

            resp.raise_for_status()
            data = resp.json()

            if total is None:
                total = data.get("page_meta", {}).get("total_count", 0)
                logger.info("ChEMBL Activities: total=%d", total)

            activities = data.get("activities", [])
            if not activities:
                break

            request_id = f"chembl_act_p{page_num}_o{offset}"
            blob = {
                "_request_id": request_id,
                "_page_number": page_num,
                "_offset": offset,
                "activities": activities,
                "page_meta": data.get("page_meta", {}),
            }
            all_blobs.append(blob)
            total_activity_count += len(activities)

            if max_records and total_activity_count >= max_records:
                logger.info("ChEMBL Activities: reached max_records=%d", max_records)
                break

            offset += _PAGE_SIZE
            page_num += 1

            if total and offset >= total:
                break

            time.sleep(_REQUEST_DELAY)

        logger.info(
            "ChEMBL Activities: fetched %d page blobs (~%d activities)",
            len(all_blobs),
            total_activity_count,
        )
        return all_blobs
