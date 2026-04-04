"""UniProt REST API Data Fetcher.

Feature: 012-platform-hardening (US3)

Fetches protein records from UniProt REST API for drug target data.
Uses the public UniProt REST API (no authentication required).

Source: https://rest.uniprot.org/
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional

from ..sources.uniprot import load_uniprot_data
from ..utils.checkpoint import clear_checkpoint, load_checkpoint, save_checkpoint
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
        """Fetch UniProt protein records, streaming pages directly to DB.

        Keyword Args:
            query: UniProt search query. Defaults to all reviewed (Swiss-Prot) proteins.
            max_results: Maximum records to fetch. Defaults to None (unlimited).

        Returns:
            Dict with keys: status, records (empty — flushed to DB), record_count, hash.
        """
        query = kwargs.get("query", self.DEFAULT_QUERY)
        raw_max = kwargs.get("max_results", self.MAX_RESULTS)
        max_results: Optional[int] = int(raw_max) if raw_max is not None else None

        try:
            total = self._stream_to_db(query, size=max_results)

            content_hash = hashlib.md5(
                f"{query}:{total}".encode()
            ).hexdigest()

            result = {
                "status": "success",
                "records": [],  # already in DB
                "record_count": total,
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": total})
            return result

        except Exception as e:
            logger.exception(f"UniProt fetch failed: {e}")
            result = {"status": "failed", "records": [], "record_count": 0, "hash": None, "error": str(e)}
            self.log_fetch_result(result)
            return result

    def _stream_to_db(self, query: str, size: Optional[int] = None) -> int:
        """Stream UniProt search results page-by-page directly to DB with checkpoint/resume.

        UniProt REST API returns up to 500 results per page. The Link header
        rel="next" provides the next page URL. Pages are written to DB immediately;
        memory is O(page_size) at all times.

        Returns:
            Total number of protein records written.
        """
        url = f"{self.BASE_URL}/search"
        page_size = min(size, 500) if size is not None else 500
        params = {
            "query": query,
            "format": "json",
            "size": str(page_size),
            "fields": (
                "accession,id,protein_name,gene_names,organism_name,"
                "length,keyword,cc_function,ft_binding,"
                "xref_pdb,xref_chembl,xref_drugbank,"
                "annotation_score,sequence"
            ),
        }

        # Resume from checkpoint if available
        cp = load_checkpoint(self.SOURCE_NAME)
        next_url: Optional[str] = url
        total = 0
        first_page = True
        if cp and cp.get("query") == query:
            resume_next = cp.get("next_url")
            if resume_next:
                next_url = resume_next
                first_page = False
            total = cp.get("total_fetched", 0)
            logger.info(
                "UniProt: resuming from checkpoint total=%d", total
            )
        elif cp:
            logger.info("UniProt: checkpoint query mismatch, starting fresh")

        while next_url and (size is None or total < size):
            if first_page:
                response = self.session.get(next_url, params=params, timeout=60)
                first_page = False
            else:
                response = self.session.get(next_url, timeout=60)
            response.raise_for_status()
            data = response.json()

            page_results: List[Dict[str, Any]] = data.get("results", [])
            if not page_results:
                break

            # Flush page directly to DB
            load_uniprot_data(page_results)
            total += len(page_results)

            # Follow Link: <url>; rel="next" header
            link_header = response.headers.get("Link", "")
            next_url = None
            if link_header:
                for part in link_header.split(","):
                    part = part.strip()
                    if 'rel="next"' in part:
                        start_idx = part.find("<") + 1
                        end_idx = part.find(">")
                        if start_idx > 0 and end_idx > start_idx:
                            next_url = part[start_idx:end_idx]
                        break

            save_checkpoint(self.SOURCE_NAME, {
                "query": query,
                "next_url": next_url,
                "total_fetched": total,
            })
            logger.debug("UniProt: page written total=%d", total)

            if len(page_results) < page_size:
                break

        clear_checkpoint(self.SOURCE_NAME)
        logger.info("UniProt streamed %d proteins to DB", total)
        return total if size is None else min(total, size)
