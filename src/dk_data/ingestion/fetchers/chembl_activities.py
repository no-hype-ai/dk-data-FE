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

Checkpoint/resume:
  Writes to meta.fetch_checkpoints after every CHECKPOINT_INTERVAL pages so
  that a pod restart or OOMKill can resume from the last committed offset
  instead of re-fetching all ~20M records from scratch.
  Checkpoint is cleared on successful completion.
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .base import BaseFetcher
from ..utils.checkpoint import clear_checkpoint, load_checkpoint, save_checkpoint
from ..sources.chembl_activities import load_chembl_activities_data

logger = logging.getLogger(__name__)

_API_URL = "https://www.ebi.ac.uk/chembl/api/data/activity.json"
_PAGE_SIZE = 1000
_REQUEST_DELAY = 1.0   # 1 req/sec — ChEMBL fair-use recommendation
_CHECKPOINT_INTERVAL = 10  # flush every 10 pages (10k activities) to stay within 512Mi pod limit


class ChEMBLActivitiesFetcher(BaseFetcher):
    """Fetcher for ChEMBL bioactivity measurements via REST API.

    Paginates through all activities using offset/limit. Commits to DB and
    saves a checkpoint every CHECKPOINT_INTERVAL pages so runs can resume
    after pod restarts rather than re-fetching from scratch.
    """

    SOURCE_NAME = "chembl_activities"
    BASE_URL = "https://www.ebi.ac.uk"

    def get_latest_url(self) -> str:
        return f"{_API_URL}?limit={_PAGE_SIZE}&offset=0"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch and load ChEMBL activity records, resuming from checkpoint if present.

        Keyword Args:
            max_records: Cap total activities fetched. Default: None (all ~20M).
            pchembl_min: Minimum pChEMBL value filter (e.g. 5.0 for sub-10µM).

        Returns:
            Dict with keys: status, records, record_count, hash, error.
            records is always [] — data is streamed directly to DB per page batch.
        """
        max_records: Optional[int] = kwargs.get("max_records")
        pchembl_min: Optional[float] = kwargs.get("pchembl_min")

        try:
            total_inserted = self._fetch_and_load(
                max_records=max_records, pchembl_min=pchembl_min
            )
            content_hash = hashlib.md5(
                json.dumps(total_inserted).encode()
            ).hexdigest()
            clear_checkpoint(self.SOURCE_NAME)

            result: Dict[str, Any] = {
                "status": "success",
                "records": [],   # streamed directly to DB — not held in memory
                "record_count": total_inserted,
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": total_inserted})
            return result

        except Exception as exc:
            logger.exception("ChEMBL activities fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_and_load(
        self,
        max_records: Optional[int],
        pchembl_min: Optional[float],
    ) -> int:
        """Page through ChEMBL activities, committing each batch to DB and checkpointing.

        Returns total page blobs inserted/updated (each blob = 1 API page).
        """
        # Resume from checkpoint if available
        cp = load_checkpoint(self.SOURCE_NAME)
        start_offset = cp.get("offset", 0) if cp else 0
        total_inserted = cp.get("records_inserted", 0) if cp else 0
        total_activity_count = cp.get("activity_count", 0) if cp else 0

        if start_offset > 0:
            logger.info(
                "ChEMBL activities: resuming from checkpoint offset=%d (%d blobs already inserted)",
                start_offset, total_inserted,
            )

        offset = start_offset
        total: Optional[int] = cp.get("total") if cp else None
        page_buffer: List[Dict[str, Any]] = []
        pages_since_checkpoint = 0
        page_num = start_offset // _PAGE_SIZE

        while True:
            params: Dict[str, Any] = {
                "limit": _PAGE_SIZE,
                "offset": offset,
                "format": "json",
            }
            if pchembl_min is not None:
                params["pchembl_value__gte"] = pchembl_min

            logger.info(
                "ChEMBL activities: page %d, offset=%d%s",
                page_num,
                offset,
                f" (total={total})" if total else "",
            )

            resp = self.session.get(_API_URL, params=params, timeout=90)

            if resp.status_code == 404:
                logger.info("ChEMBL activities: 404 at offset=%d — end of results", offset)
                break

            resp.raise_for_status()
            data = resp.json()

            if total is None:
                total = data.get("page_meta", {}).get("total_count", 0)
                logger.info("ChEMBL activities: total_count=%d", total)

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
            page_buffer.append(blob)
            total_activity_count += len(activities)
            pages_since_checkpoint += 1
            offset += _PAGE_SIZE
            page_num += 1

            # Commit and checkpoint every CHECKPOINT_INTERVAL pages
            if pages_since_checkpoint >= _CHECKPOINT_INTERVAL:
                result = load_chembl_activities_data(page_buffer)
                total_inserted += result.get("records_inserted", 0)
                page_buffer = []
                pages_since_checkpoint = 0
                save_checkpoint(self.SOURCE_NAME, {
                    "offset": offset,
                    "total": total,
                    "records_inserted": total_inserted,
                    "activity_count": total_activity_count,
                })
                logger.info(
                    "ChEMBL activities: checkpoint saved offset=%d/%d "
                    "total_blobs=%d total_activities=%d",
                    offset, total or 0, total_inserted, total_activity_count,
                )

            if max_records and total_activity_count >= max_records:
                logger.info("ChEMBL activities: reached max_records=%d", max_records)
                break

            if total and offset >= total:
                break

            time.sleep(_REQUEST_DELAY)

        # Flush remaining buffer
        if page_buffer:
            result = load_chembl_activities_data(page_buffer)
            total_inserted += result.get("records_inserted", 0)

        logger.info(
            "ChEMBL activities: complete — %d page blobs inserted (~%d activities)",
            total_inserted, total_activity_count,
        )
        return total_inserted
