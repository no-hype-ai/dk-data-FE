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

    # Default query: reviewed human proteins that are drug targets
    DEFAULT_QUERY = "(reviewed:true) AND (organism_id:9606) AND (keyword:KW-0621)"
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

        data = self.fetch_json(url, params=params)
        results = data.get("results", [])
        logger.info(f"UniProt search returned {len(results)} proteins")
        return results
