"""RCSB PDB Search API Data Fetcher.

Feature: 012-platform-hardening (US3)

Fetches protein structure records from RCSB PDB for structural biology data.
Uses the RCSB PDB Search API (no authentication required).
Implements offset-based pagination to retrieve all pharma-relevant structures.

Source: https://search.rcsb.org/
"""

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# RCSB polite delay between paginated requests
_PDB_DELAY = 0.1

# Default pharma-relevant IPC filter query
_DEFAULT_QUERY = "drug"


class PDBFetcher(BaseFetcher):
    """Fetcher for RCSB PDB structure data with full pagination."""

    SOURCE_NAME = "pdb"
    BASE_URL = "https://search.rcsb.org/rcsbsearch/v2"
    DATA_URL = "https://data.rcsb.org/rest/v1/core/entry"

    # RCSB caps at 250 results per paginated request
    PAGE_SIZE = 250

    # Default: fetch all pharma-relevant structures (several thousand)
    MAX_RESULTS = 5_000

    def get_latest_url(self) -> str:
        return f"{self.BASE_URL}/query"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch PDB structure records with full offset pagination.

        Keyword Args:
            query_text: Text search query. Defaults to 'drug'.
            max_results: Maximum records. Defaults to MAX_RESULTS.
            resume: If True, resume from last saved offset (default True).

        Returns:
            Dict with keys: status, records, hash, error (on failure).
        """
        query_text = kwargs.get("query_text", _DEFAULT_QUERY)
        max_results = kwargs.get("max_results", self.MAX_RESULTS)
        resume = kwargs.get("resume", True)

        manifest = self.load_manifest()
        start_offset: int = manifest.get("last_offset", 0) if resume else 0

        try:
            pdb_ids = self._search_paginated(query_text, max_results=max_results,
                                             start_offset=start_offset)

            if not pdb_ids:
                result = {
                    "status": "success",
                    "records": [],
                    "hash": None,
                    "message": "No structures found",
                }
                self.log_fetch_result(result)
                return result

            logger.info(f"[pdb] Fetching details for {len(pdb_ids)} structures")
            records = self._fetch_details(pdb_ids)

            content_hash = hashlib.md5(
                ",".join(sorted(pdb_ids)).encode()
            ).hexdigest()

            self.save_manifest(
                last_run_at=datetime.now(timezone.utc).isoformat(),
                last_run_status="completed",
                total_records_fetched=len(records),
                last_content_hash=content_hash,
                last_offset=0,  # Reset offset — run completed cleanly
            )

            result = {"status": "success", "records": records, "hash": content_hash}
            self.log_fetch_result({**result, "records": len(records)})
            return result

        except Exception as e:
            logger.exception(f"PDB fetch failed: {e}")
            self.save_manifest(last_run_status="interrupted")
            result = {"status": "failed", "records": [], "hash": None, "error": str(e)}
            self.log_fetch_result(result)
            return result

    def _search_paginated(
        self,
        query_text: str,
        max_results: int = 5_000,
        start_offset: int = 0,
    ) -> List[str]:
        """Search RCSB PDB with offset pagination and return all matching PDB IDs."""
        url = f"{self.BASE_URL}/query"
        all_ids: List[str] = []
        start = start_offset
        page = 0

        while len(all_ids) < max_results:
            page += 1
            rows = min(self.PAGE_SIZE, max_results - len(all_ids))

            query = {
                "query": {
                    "type": "terminal",
                    "service": "full_text",
                    "parameters": {"value": query_text},
                },
                "return_type": "entry",
                "request_options": {
                    "paginate": {"start": start, "rows": rows},
                    "results_content_type": ["experimental"],
                    "sort": [{"sort_by": "score", "direction": "desc"}],
                },
            }

            logger.debug(f"[pdb] Page {page} start={start} rows={rows}")

            response = self.session.post(url, json=query, timeout=60)
            response.raise_for_status()
            data = response.json()

            result_set = data.get("result_set", [])
            ids = [r["identifier"] for r in result_set]
            if not ids:
                break

            all_ids.extend(ids)
            total_count = data.get("total_count", 0)
            start += len(ids)

            # Save progress so an interrupted run can resume
            self.save_manifest(last_offset=start, last_run_status="in_progress")

            if start >= total_count:
                break

            time.sleep(_PDB_DELAY)

        logger.info(f"[pdb] Collected {len(all_ids)} PDB IDs in {page} pages")
        return all_ids[:max_results]

    def _fetch_details(self, pdb_ids: List[str]) -> List[Dict[str, Any]]:
        """Fetch entry details for a list of PDB IDs."""
        records = []
        for pdb_id in pdb_ids:
            try:
                url = f"{self.DATA_URL}/{pdb_id}"
                data = self.fetch_json(url)
                records.append({
                    "pdb_id": pdb_id,
                    "title": data.get("struct", {}).get("title"),
                    "method": (data.get("exptl", [{}])[0].get("method")
                               if data.get("exptl") else None),
                    "resolution": (
                        data.get("rcsb_entry_info", {}).get("resolution_combined", [None])[0]
                        if data.get("rcsb_entry_info") else None
                    ),
                    "deposit_date": data.get("rcsb_accession_info", {}).get("deposit_date"),
                    "raw_response": data,
                })
            except Exception as e:
                logger.warning(f"[pdb] Failed to fetch details for {pdb_id}: {e}")
        return records
