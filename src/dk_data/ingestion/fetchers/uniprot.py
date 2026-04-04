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

    # Default query: all reviewed (Swiss-Prot) proteins — the curated subset of UniProt
    # (570K entries). Previously restricted to human+pharmaceutical keyword (~51 results).
    DEFAULT_QUERY = "reviewed:true"
    MAX_RESULTS = None  # no cap — fetch all reviewed proteins

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
        raw_max = kwargs.get("max_results", self.MAX_RESULTS)
        max_results = int(raw_max) if raw_max is not None else None

        try:
            records = self._search(query, size=max_results)

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

    def _search(self, query: str, size=None) -> List[Dict[str, Any]]:
        """Search UniProt and return protein records.

        UniProt REST API returns up to 500 results per page. For queries that
        exceed 500 results, the response includes a Link header with rel="next"
        pointing to the next page URL. We follow these links until exhausted or
        max_results reached.
        """
        url = f"{self.BASE_URL}/search"
        page_size = min(size, 500) if size is not None else 500
        params = {
            "query": query,
            "format": "json",
            "size": str(page_size),
            # UniProt REST API v2 field names for JSON format.
            # These return the full nested objects needed by the bronze SQL model:
            #   accession         → primaryAccession
            #   id                → uniProtkbId (entry name)
            #   protein_name      → proteinDescription (recommendedName, alternativeNames)
            #   gene_names        → genes array
            #   organism_name     → organism (scientificName, commonName, taxonId, lineage)
            #   length            → sequence.length (also sequence.value, molWeight, checksum)
            #   keyword           → keywords
            #   cc_function       → comments (FUNCTION type)
            #   ft_binding        → features (BINDING type)
            #   xref_pdb          → uniProtKBCrossReferences filtered to PDB
            #   xref_go           → uniProtKBCrossReferences filtered to GO
            #   annotation_score  → annotationScore
            "fields": (
                "accession,id,protein_name,gene_names,organism_name,"
                "length,keyword,cc_function,ft_binding,"
                "xref_pdb,xref_chembl,xref_drugbank,"
                "annotation_score,sequence"
            ),
        }

        all_results: List[Dict[str, Any]] = []
        next_url = url

        while next_url and (size is None or len(all_results) < size):
            if next_url == url:
                response = self.session.get(next_url, params=params, timeout=60)
            else:
                # Subsequent pages: URL already includes all params from Link header
                response = self.session.get(next_url, timeout=60)
            response.raise_for_status()
            data = response.json()

            page_results = data.get("results", [])
            all_results.extend(page_results)

            # Follow Link: <url>; rel="next" header for pagination beyond 500
            link_header = response.headers.get("Link", "")
            next_url = None
            if link_header:
                for part in link_header.split(","):
                    part = part.strip()
                    if 'rel="next"' in part:
                        # Extract URL from <url> format
                        start = part.find("<") + 1
                        end = part.find(">")
                        if start > 0 and end > start:
                            next_url = part[start:end]
                        break

            if len(page_results) < page_size:
                # Last page — fewer results than requested
                break

        logger.info("UniProt search returned %d proteins", len(all_results))
        return all_results[:size] if size is not None else all_results
