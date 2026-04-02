"""ChEMBL Molecules fetcher — chemical entities of biological interest.

Fetches small-molecule compound records from the ChEMBL REST API. ChEMBL
is the authoritative source for medicinal chemistry compounds with
bioactivity data.

API: https://www.ebi.ac.uk/chembl/api/data/molecule.json
  Public, no authentication required.
  Pagination via offset/limit (limit=1000 per request).
  Total: ~2.4M compounds.
  Response: {"molecules": [...], "page_meta": {"total_count": N, "limit": L, "offset": O}}

Stores one JSONB record per compound in mol_raw.chembl.

Checkpoint/resume:
  Writes to meta.fetch_checkpoints after every CHECKPOINT_INTERVAL pages so
  that a pod restart or OOMKill can resume from the last committed offset
  instead of re-fetching all ~2.4M records from scratch.
  Checkpoint is cleared on successful completion.
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .base import BaseFetcher
from ..utils.checkpoint import clear_checkpoint, load_checkpoint, save_checkpoint
from ..sources.chembl_molecules import load_chembl_molecules_data

logger = logging.getLogger(__name__)

_API_URL = "https://www.ebi.ac.uk/chembl/api/data/molecule.json"
_PAGE_SIZE = 1000
_REQUEST_DELAY = 0.2
_CHECKPOINT_INTERVAL = 50  # save checkpoint every 50 pages (= 50k records)


class ChEMBLMoleculesFetcher(BaseFetcher):
    """Fetcher for ChEMBL compound records via the ChEMBL REST API.

    Paginates through all molecules using offset/limit. Commits to DB and
    saves a checkpoint every CHECKPOINT_INTERVAL pages so runs can resume
    after pod restarts rather than re-fetching from scratch.
    """

    SOURCE_NAME = "chembl_molecules"
    BASE_URL = "https://www.ebi.ac.uk/chembl/api/data"

    def get_latest_url(self) -> str:
        return f"{_API_URL}?format=json&limit={_PAGE_SIZE}&offset=0"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch and load ChEMBL molecule records, resuming from checkpoint if present.

        Keyword Args:
            max_records: Cap total records fetched. Default: None (all ~2.4M).

        Returns:
            Dict with keys: status, records, record_count, hash, error.
            records is always [] — data is streamed directly to DB per page batch.
        """
        max_records: Optional[int] = kwargs.get("max_records")

        try:
            total_inserted = self._fetch_and_load(max_records=max_records)
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
            logger.exception("ChEMBL molecules fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_and_load(self, max_records: Optional[int]) -> int:
        """Page through ChEMBL, committing each batch to DB and checkpointing.

        Returns total records inserted/updated.
        """
        # Resume from checkpoint if available
        cp = load_checkpoint(self.SOURCE_NAME)
        start_offset = cp.get("offset", 0) if cp else 0
        total_inserted = cp.get("records_inserted", 0) if cp else 0

        if start_offset > 0:
            logger.info(
                "ChEMBL: resuming from checkpoint offset=%d (%d already inserted)",
                start_offset, total_inserted,
            )

        offset = start_offset
        total: Optional[int] = cp.get("total") if cp else None
        page_buffer: List[Dict[str, Any]] = []
        pages_since_checkpoint = 0

        while True:
            params: Dict[str, Any] = {
                "format": "json",
                "limit": _PAGE_SIZE,
                "offset": offset,
            }

            resp = self.session.get(_API_URL, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()

            if total is None:
                page_meta = data.get("page_meta", {})
                total = page_meta.get("total_count", 0)
                logger.info("ChEMBL: total_count=%d", total)

            molecules = data.get("molecules", [])
            if not molecules:
                break

            page_buffer.extend(molecules)
            pages_since_checkpoint += 1
            offset += _PAGE_SIZE

            # Commit and checkpoint every CHECKPOINT_INTERVAL pages
            if pages_since_checkpoint >= _CHECKPOINT_INTERVAL:
                result = load_chembl_molecules_data(page_buffer)
                total_inserted += result.get("records_inserted", 0)
                page_buffer = []
                pages_since_checkpoint = 0
                save_checkpoint(self.SOURCE_NAME, {
                    "offset": offset,
                    "total": total,
                    "records_inserted": total_inserted,
                })
                logger.info(
                    "ChEMBL: checkpoint saved offset=%d/%d total_inserted=%d",
                    offset, total or 0, total_inserted,
                )

            if max_records and (total_inserted + len(page_buffer)) >= max_records:
                break

            page_meta = data.get("page_meta", {})
            if not page_meta.get("next"):
                break

            if total and offset >= total:
                break

            time.sleep(_REQUEST_DELAY)

        # Flush remaining buffer
        if page_buffer:
            result = load_chembl_molecules_data(page_buffer)
            total_inserted += result.get("records_inserted", 0)

        logger.info("ChEMBL: complete — %d total inserted/updated", total_inserted)
        return total_inserted
