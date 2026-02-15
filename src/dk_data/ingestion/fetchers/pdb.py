"""RCSB PDB Search API Data Fetcher.

Feature: 012-platform-hardening (US3)

Fetches protein structure records from RCSB PDB for structural biology data.
Uses the RCSB PDB Search API (no authentication required).

Source: https://search.rcsb.org/
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

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
        """Search RCSB PDB and return PDB IDs."""
        url = f"{self.BASE_URL}/query"
        query = {
            "query": {
                "type": "terminal",
                "service": "full_text",
                "parameters": {"value": query_text},
            },
            "return_type": "entry",
            "request_options": {
                "paginate": {"start": 0, "rows": min(max_results, 500)},
                "results_content_type": ["experimental"],
            },
        }

        response = self.session.post(url, json=query, timeout=60)
        response.raise_for_status()
        data = response.json()

        return [r["identifier"] for r in data.get("result_set", [])]

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
                    "method": (data.get("exptl", [{}])[0].get("method") if data.get("exptl") else None),
                    "resolution": (data.get("rcsb_entry_info", {}).get("resolution_combined", [None])[0]
                                   if data.get("rcsb_entry_info") else None),
                    "deposit_date": data.get("rcsb_accession_info", {}).get("deposit_date"),
                    "raw_response": data,
                })
            except Exception as e:
                logger.warning(f"Failed to fetch details for {pdb_id}: {e}")
        return records
