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

Checkpoint/resume:
  Writes to meta.fetch_checkpoints after every CHECKPOINT_INTERVAL pages so
  that a pod restart or OOMKill can resume from the last committed skip offset
  instead of re-fetching all records from scratch.
  Checkpoint is cleared on successful completion.
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .base import BaseFetcher
from ..utils.checkpoint import clear_checkpoint, load_checkpoint, save_checkpoint
from ..sources.npi_registry import load_npi_registry_data

logger = logging.getLogger(__name__)

_API_URL = "https://npiregistry.cms.hhs.gov/api/"
_PAGE_SIZE = 200
_REQUEST_DELAY = 0.2
_MAX_SKIP = 1_000_000
_CHECKPOINT_INTERVAL = 250  # save checkpoint every 250 pages (= 50k records)


class NPIRegistryFetcher(BaseFetcher):
    """Fetcher for CMS NPI Registry provider records.

    Paginates through all active NPIs using skip/limit. Commits to DB and
    saves a checkpoint every CHECKPOINT_INTERVAL pages so runs can resume
    after pod restarts rather than re-fetching from scratch.
    """

    SOURCE_NAME = "npi_registry"
    BASE_URL = "https://npiregistry.cms.hhs.gov/api"

    def get_latest_url(self) -> str:
        return f"{_API_URL}?version=2.1&limit={_PAGE_SIZE}&skip=0"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch and load NPI Registry provider records, resuming from checkpoint if present.

        Keyword Args:
            max_records: Cap total records. Default: None (all, capped at 1M).

        Returns:
            Dict with keys: status, records, record_count, hash, error.
            records is always [] — data is streamed directly to DB per page batch.
        """
        max_records: Optional[int] = kwargs.get("max_records")
        effective_max = min(max_records, _MAX_SKIP) if max_records else _MAX_SKIP

        try:
            total_inserted = self._fetch_and_load(max_records=effective_max)
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

    def _fetch_and_load(self, max_records: int) -> int:
        """Page through NPI Registry, committing each batch to DB and checkpointing.

        Returns total records inserted/updated.
        """
        # Resume from checkpoint if available
        cp = load_checkpoint(self.SOURCE_NAME)
        skip = cp.get("skip", 0) if cp else 0
        total_inserted = cp.get("records_inserted", 0) if cp else 0

        if skip > 0:
            logger.info(
                "NPI Registry: resuming from checkpoint skip=%d (%d already inserted)",
                skip, total_inserted,
            )

        record_buffer: List[Dict[str, Any]] = []
        pages_since_checkpoint = 0
        total_fetched = skip  # records processed so far (including prior checkpoint)

        while total_fetched < max_records:
            remaining = max_records - total_fetched
            limit = min(_PAGE_SIZE, remaining)

            params: Dict[str, Any] = {
                "version": "2.1",
                "limit": limit,
                "skip": total_fetched,
            }

            logger.debug("NPI Registry: skip=%d limit=%d", total_fetched, limit)

            try:
                resp = self.session.get(_API_URL, params=params, timeout=60)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning(
                    "NPI Registry request failed at skip=%d: %s", total_fetched, exc
                )
                break

            results = data.get("results", [])
            if not results:
                logger.info("NPI Registry: empty page at skip=%d — done", total_fetched)
                break

            record_buffer.extend(results)
            total_fetched += len(results)
            pages_since_checkpoint += 1

            logger.info(
                "NPI Registry: skip=%d fetched %d records (running total=%d)",
                total_fetched - len(results), len(results), total_fetched,
            )

            # Commit and checkpoint every CHECKPOINT_INTERVAL pages
            if pages_since_checkpoint >= _CHECKPOINT_INTERVAL:
                result = load_npi_registry_data(record_buffer)
                total_inserted += result.get("records_inserted", 0)
                record_buffer = []
                pages_since_checkpoint = 0
                save_checkpoint(self.SOURCE_NAME, {
                    "skip": total_fetched,
                    "records_inserted": total_inserted,
                })
                logger.info(
                    "NPI Registry: checkpoint saved skip=%d total_inserted=%d",
                    total_fetched, total_inserted,
                )

            if len(results) < limit:
                break

            if total_fetched >= _MAX_SKIP:
                logger.warning(
                    "NPI Registry: reached skip cap (%d) with %d records",
                    _MAX_SKIP, total_fetched,
                )
                break

            time.sleep(_REQUEST_DELAY)

        # Flush remaining buffer
        if record_buffer:
            result = load_npi_registry_data(record_buffer)
            total_inserted += result.get("records_inserted", 0)

        logger.info("NPI Registry: complete — %d total inserted/updated", total_inserted)
        return total_inserted
