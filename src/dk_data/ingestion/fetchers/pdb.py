"""RCSB PDB Search API Data Fetcher.

Feature: 012-platform-hardening (US3)

Fetches protein structure records from RCSB PDB for structural biology data.
Uses the RCSB PDB Search API (no authentication required).

Source: https://search.rcsb.org/

Self-loading with checkpoint/resume:
  Phase 1: Collect all matching PDB IDs (500/page, held in memory — ~800 KB for 200K IDs).
  Phase 2: Fetch detail records one-by-one and flush batches of DETAIL_BATCH_SIZE to DB.
  Checkpoint stores the full ID list + the index of the last committed detail record,
  so a pod restart skips both the ID collection phase and already-committed details.
"""

import hashlib
import logging
import time
from typing import Any, Dict, List, Optional

from ..sources.pdb import load_pdb_data
from ..utils.checkpoint import clear_checkpoint, load_checkpoint, save_checkpoint
from .base import BaseFetcher

logger = logging.getLogger(__name__)

# How many detail records to flush to DB at once
DETAIL_BATCH_SIZE = 100


class PDBFetcher(BaseFetcher):
    """Fetcher for RCSB PDB structure data."""

    SOURCE_NAME = "pdb"
    BASE_URL = "https://search.rcsb.org/rcsbsearch/v2"
    DATA_URL = "https://data.rcsb.org/rest/v1/core/entry"

    MAX_RESULTS = None  # no cap — fetch all matching structures

    def get_latest_url(self) -> str:
        return f"{self.BASE_URL}/query"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch PDB structure records, streaming detail batches directly to DB.

        Keyword Args:
            query_text: Text search query. Defaults to None (all experimental structures).
            max_results: Maximum records. Defaults to None (unlimited).

        Returns:
            Dict with keys: status, records (empty — flushed to DB), record_count, hash.
        """
        query_text = kwargs.get("query_text", None)
        raw_max = kwargs.get("max_results", self.MAX_RESULTS)
        max_results: Optional[int] = int(raw_max) if raw_max is not None else None

        try:
            # Resume from checkpoint if available
            cp = load_checkpoint(self.SOURCE_NAME)
            pdb_ids: Optional[List[str]] = None
            resume_idx = 0
            prior_total = 0

            if cp:
                pdb_ids = cp.get("pdb_ids")
                resume_idx = cp.get("detail_idx", 0)
                prior_total = cp.get("total_fetched", 0)
                if pdb_ids:
                    logger.info(
                        "PDB: resuming from checkpoint detail_idx=%d / %d total_ids=%d",
                        resume_idx, prior_total, len(pdb_ids),
                    )

            # Phase 1: collect IDs if not already checkpointed
            if not pdb_ids:
                pdb_ids = self._search(query_text, max_results=max_results)
                if not pdb_ids:
                    result = {
                        "status": "success",
                        "records": [],
                        "record_count": 0,
                        "hash": None,
                        "message": "No structures found",
                    }
                    self.log_fetch_result(result)
                    return result

                logger.info("PDB: collected %d structure IDs", len(pdb_ids))
                # Save IDs immediately so Phase 2 can resume without re-collecting
                save_checkpoint(self.SOURCE_NAME, {
                    "pdb_ids": pdb_ids,
                    "detail_idx": 0,
                    "total_fetched": 0,
                })

            content_hash = hashlib.md5(
                ",".join(sorted(pdb_ids)).encode()
            ).hexdigest()

            # Phase 2: fetch details, flushing every DETAIL_BATCH_SIZE records
            total = prior_total
            batch: List[Dict[str, Any]] = []

            for i in range(resume_idx, len(pdb_ids)):
                pdb_id = pdb_ids[i]
                try:
                    url = f"{self.DATA_URL}/{pdb_id}"
                    data = self.fetch_json(url)
                    batch.append({
                        "pdb_id": pdb_id,
                        "title": data.get("struct", {}).get("title"),
                        "method": (
                            data.get("exptl", [{}])[0].get("method")
                            if data.get("exptl") else None
                        ),
                        "resolution": (
                            data.get("rcsb_entry_info", {}).get("resolution_combined", [None])[0]
                            if data.get("rcsb_entry_info") else None
                        ),
                        "deposit_date": data.get("rcsb_accession_info", {}).get("deposit_date"),
                        "raw_response": data,
                    })
                except Exception as e:
                    logger.warning("PDB: failed to fetch details for %s: %s", pdb_id, e)

                # Flush batch and checkpoint every DETAIL_BATCH_SIZE entries
                if len(batch) >= DETAIL_BATCH_SIZE:
                    load_pdb_data(batch)
                    total += len(batch)
                    batch = []
                    save_checkpoint(self.SOURCE_NAME, {
                        "pdb_ids": pdb_ids,
                        "detail_idx": i + 1,
                        "total_fetched": total,
                    })
                    logger.info("PDB: checkpoint idx=%d total=%d", i + 1, total)

                # Polite inter-request delay (~10 req/s)
                if i < len(pdb_ids) - 1:
                    time.sleep(0.1)

            # Flush remaining
            if batch:
                load_pdb_data(batch)
                total += len(batch)

            clear_checkpoint(self.SOURCE_NAME)

            result = {"status": "success", "records": [], "record_count": total, "hash": content_hash}
            self.log_fetch_result({"status": "success", "records": total})
            return result

        except Exception as e:
            logger.exception(f"PDB fetch failed: {e}")
            result = {"status": "failed", "records": [], "record_count": 0, "hash": None, "error": str(e)}
            self.log_fetch_result(result)
            return result

    def _search(self, query_text=None, max_results=None) -> List[str]:
        """Search RCSB PDB and return PDB IDs.

        RCSB PDB Search API v2 returns at most 500 entries per page.
        Pages through results via the paginate.start offset until max_results
        are collected or no more results are available.
        If query_text is None, fetches all experimental structures (no text filter).
        """
        url = f"{self.BASE_URL}/query"
        page_size = 500  # RCSB hard limit per request
        all_ids: List[str] = []
        start = 0

        while max_results is None or len(all_ids) < max_results:
            rows = min(page_size, (max_results - len(all_ids)) if max_results is not None else page_size)
            if query_text:
                query_node = {
                    "type": "terminal",
                    "service": "full_text",
                    "parameters": {"value": query_text},
                }
            else:
                # Match all experimental structures
                query_node = {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "rcsb_entry_info.experimental_method_count",
                        "operator": "greater",
                        "value": 0,
                    },
                }
            query = {
                "query": query_node,
                "return_type": "entry",
                "request_options": {
                    "paginate": {"start": start, "rows": rows},
                    "results_content_type": ["experimental"],
                },
            }

            # RCSB PDB search is slow under load — extended to 180s (#189 timeout fix)
            response = self.session.post(url, json=query, timeout=180)
            response.raise_for_status()
            data = response.json()

            page_ids = [r["identifier"] for r in data.get("result_set", [])]
            if not page_ids:
                break
            all_ids.extend(page_ids)
            logger.debug("[pdb] fetched %d IDs (start=%d, total=%d)", len(page_ids), start, len(all_ids))

            if len(page_ids) < rows:
                break  # last page
            start += rows

        logger.info("[pdb] %d total structure IDs collected", len(all_ids))
        return all_ids
