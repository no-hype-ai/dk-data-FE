"""RCSB PDB Search API Data Fetcher.

Feature: 012-platform-hardening (US3)

Fetches protein structure records from RCSB PDB for structural biology data.
Uses the RCSB PDB Search API (no authentication required).

Source: https://search.rcsb.org/
"""

import hashlib
import logging
import time
from typing import Any, Dict, List

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class PDBFetcher(BaseFetcher):
    """Fetcher for RCSB PDB structure data."""

    SOURCE_NAME = "pdb"
    BASE_URL = "https://search.rcsb.org/rcsbsearch/v2"
    DATA_URL = "https://data.rcsb.org/rest/v1/core/entry"

    MAX_RESULTS = 500

    def get_latest_url(self) -> str:
        return f"{self.BASE_URL}/query"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch PDB structure records.

        Keyword Args:
            query_text: Text search query. Defaults to drug-like ligands.
            max_results: Maximum records. Defaults to 500.

        Returns:
            Dict with keys: status, records, hash, error (on failure).
        """
        query_text = kwargs.get("query_text", "drug target")
        max_results = kwargs.get("max_results", self.MAX_RESULTS)

        try:
            pdb_ids = self._search(query_text, max_results=max_results)

            if not pdb_ids:
                result = {
                    "status": "success",
                    "records": [],
                    "hash": None,
                    "message": "No structures found",
                }
                self.log_fetch_result(result)
                return result

            logger.info(f"PDB search returned {len(pdb_ids)} structure IDs")

            # Fetch details for each PDB ID
            records = self._fetch_details(pdb_ids)

            content_hash = hashlib.md5(
                ",".join(sorted(pdb_ids)).encode()
            ).hexdigest()

            result = {"status": "success", "records": records, "hash": content_hash}
            self.log_fetch_result({**result, "records": len(records)})
            return result

        except Exception as e:
            logger.exception(f"PDB fetch failed: {e}")
            result = {"status": "failed", "records": [], "hash": None, "error": str(e)}
            self.log_fetch_result(result)
            return result

    def _search(self, query_text: str, max_results: int = 500) -> List[str]:
        """Search RCSB PDB and return PDB IDs.

        RCSB PDB Search API v2 returns at most 500 entries per page.
        Pages through results via the paginate.start offset until max_results
        are collected or no more results are available.
        """
        url = f"{self.BASE_URL}/query"
        page_size = 500  # RCSB hard limit per request
        all_ids: List[str] = []
        start = 0

        while len(all_ids) < max_results:
            rows = min(page_size, max_results - len(all_ids))
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

    def _fetch_details(self, pdb_ids: List[str]) -> List[Dict[str, Any]]:
        """Fetch entry details for a list of PDB IDs.

        RCSB PDB recommends "a handful of requests per second". 0.1s delay
        (~10 req/s) is polite for sequential per-ID calls.
        """
        records = []
        for i, pdb_id in enumerate(pdb_ids):
            try:
                url = f"{self.DATA_URL}/{pdb_id}"
                data = self.fetch_json(url)
                records.append({
                    "pdb_id": pdb_id,
                    "title": data.get("struct", {}).get("title"),
                    "method": (data.get("exptl", [{}])[0].get("method") if data.get("exptl") else None),
                    "resolution": (data.get("rcsb_entry_info", {}).get("resolution_combined", [None])[0]
                                   if data.get("rcsb_entry_info") else None),
                    "deposit_date": data.get("rcsb_accession_info", {}).get("deposit_date"),
                    "raw_response": data,
                })
            except Exception as e:
                logger.warning(f"Failed to fetch details for {pdb_id}: {e}")
            # Polite inter-request delay — RCSB does not publish a hard limit
            # but rate-limits aggressively on shared IPs; 100ms keeps us ~10 req/s.
            if i < len(pdb_ids) - 1:
                time.sleep(0.1)
        return records
