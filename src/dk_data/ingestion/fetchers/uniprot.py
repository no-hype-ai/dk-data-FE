"""UniProt REST API Data Fetcher.

Feature: 012-platform-hardening (US3)

Fetches protein records from UniProt REST API for drug target data.
Uses the public UniProt REST API (no authentication required).

Source: https://rest.uniprot.org/
"""

import hashlib
import logging
from typing import Any, Dict, List

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class UniProtFetcher(BaseFetcher):
    """Fetcher for UniProt protein data via REST API."""

    SOURCE_NAME = "uniprot"
    BASE_URL = "https://rest.uniprot.org/uniprotkb"

    # Default query: reviewed human proteins with Pharmaceutical keyword.
    # KW-0621 (Polymorphism) returned 0 results in smoke tests.
    # KW-9993 (Pharmaceutical) is the correct keyword for drug targets.
    # Fallback: omit keyword filter entirely and rely on size limit.
    DEFAULT_QUERY = "(reviewed:true) AND (organism_id:9606) AND (keyword:KW-9993)"
    FALLBACK_QUERY = "(reviewed:true) AND (organism_id:9606)"
    MAX_RESULTS = 500

    def get_latest_url(self) -> str:
        return f"{self.BASE_URL}/search"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch UniProt protein records.

        Keyword Args:
            query: UniProt search query. Defaults to reviewed human drug targets.
            max_results: Maximum records to fetch. Defaults to 500.

        Returns:
            Dict with keys: status, records, hash, error (on failure).
        """
        query = kwargs.get("query", self.DEFAULT_QUERY)
        max_results = kwargs.get("max_results", self.MAX_RESULTS)

        try:
            records = self._search(query, size=max_results)

            # If primary query returns empty, try fallback (broader query)
            if not records and query == self.DEFAULT_QUERY:
                logger.info(
                    "UniProt primary query returned 0 results, trying fallback query"
                )
                records = self._search(self.FALLBACK_QUERY, size=max_results)

            content_hash = hashlib.md5(
                ",".join(sorted(r.get("primaryAccession", "") for r in records)).encode()
            ).hexdigest() if records else None

            result = {
                "status": "success",
                "records": records,
                "hash": content_hash,
            }
            self.log_fetch_result({**result, "records": len(records)})
            return result

        except Exception as e:
            logger.exception(f"UniProt fetch failed: {e}")
            result = {"status": "failed", "records": [], "hash": None, "error": str(e)}
            self.log_fetch_result(result)
            return result

    def _search(self, query: str, size: int = 500) -> List[Dict[str, Any]]:
        """Search UniProt and return protein records."""
        url = f"{self.BASE_URL}/search"
        params = {
            "query": query,
            "format": "json",
            "size": str(min(size, 500)),
            "fields": "accession,id,gene_names,organism_name,protein_name,length,keyword,ft_binding,cc_function",
        }

        data = self.fetch_json(url, params=params)
        results = data.get("results", [])
        logger.info(f"UniProt search returned {len(results)} proteins")
        return results
