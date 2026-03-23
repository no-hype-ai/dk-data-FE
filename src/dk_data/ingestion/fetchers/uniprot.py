"""UniProt REST API Data Fetcher.

Feature: 012-platform-hardening (US3)

Fetches protein records from UniProt REST API for drug target data.
Uses the public UniProt REST API (no authentication required).
Implements cursor-based pagination via the Link header to retrieve
the full result set (20K+ reviewed human proteins).

Source: https://rest.uniprot.org/
"""

import hashlib
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# UniProt allows 200 ms between requests in the polite pool
_UNIPROT_DELAY = 0.2


class UniProtFetcher(BaseFetcher):
    """Fetcher for UniProt protein data via REST API with full pagination."""

    SOURCE_NAME = "uniprot"
    BASE_URL = "https://rest.uniprot.org/uniprotkb"

    # Reviewed human drug-target proteins (KW-9993 = Pharmaceutical)
    DEFAULT_QUERY = "(reviewed:true) AND (organism_id:9606) AND (keyword:KW-9993)"
    FALLBACK_QUERY = "(reviewed:true) AND (organism_id:9606)"

    # UniProt max page size
    PAGE_SIZE = 500

    # Default cap: fetch all reviewed human pharma proteins (~5K records)
    MAX_RESULTS = 10_000

    def get_latest_url(self) -> str:
        return f"{self.BASE_URL}/search"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch UniProt protein records with full cursor pagination.

        Keyword Args:
            query: UniProt search query. Defaults to reviewed human drug targets.
            max_results: Maximum records to fetch. Defaults to MAX_RESULTS.
            resume: If True, resume from last saved cursor (default True).

        Returns:
            Dict with keys: status, records, hash, error (on failure).
        """
        query = kwargs.get("query", self.DEFAULT_QUERY)
        max_results = kwargs.get("max_results", self.MAX_RESULTS)
        resume = kwargs.get("resume", True)

        manifest = self.load_manifest()
        resume_cursor: Optional[str] = manifest.get("last_cursor") if resume else None

        try:
            records = self._search_paginated(query, max_results=max_results,
                                             resume_cursor=resume_cursor)

            if not records and query == self.DEFAULT_QUERY:
                logger.info("UniProt primary query returned 0 results, trying fallback")
                records = self._search_paginated(self.FALLBACK_QUERY,
                                                 max_results=max_results)

            content_hash = hashlib.md5(
                ",".join(sorted(r.get("primaryAccession", "") for r in records)).encode()
            ).hexdigest() if records else None

            self.save_manifest(
                last_run_at=datetime.now(timezone.utc).isoformat(),
                last_run_status="completed",
                total_records_fetched=len(records),
                last_content_hash=content_hash,
                last_cursor=None,  # Clear cursor — run completed cleanly
            )

            result = {"status": "success", "records": records, "hash": content_hash}
            self.log_fetch_result({**result, "records": len(records)})
            return result

        except Exception as e:
            logger.exception(f"UniProt fetch failed: {e}")
            self.save_manifest(last_run_status="interrupted")
            result = {"status": "failed", "records": [], "hash": None, "error": str(e)}
            self.log_fetch_result(result)
            return result

    def _search_paginated(
        self,
        query: str,
        max_results: int = 10_000,
        resume_cursor: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search UniProt using Link-header cursor pagination.

        UniProt REST API v1 returns a `Link: <url>; rel="next"` header
        when there are more pages. We follow it until exhausted or until
        max_results is reached.
        """
        all_records: List[Dict[str, Any]] = []

        # First request: use resume_cursor URL if provided, else build from scratch
        if resume_cursor:
            url: Optional[str] = resume_cursor
            params: Optional[Dict] = None
            logger.info(f"[uniprot] Resuming from saved cursor")
        else:
            url = f"{self.BASE_URL}/search"
            params = {
                "query": query,
                "format": "json",
                "size": str(self.PAGE_SIZE),
                "fields": (
                    "accession,id,gene_names,organism_name,protein_name,"
                    "length,keyword,ft_binding,cc_function,sequence"
                ),
            }

        page = 0
        while url and len(all_records) < max_results:
            page += 1
            logger.debug(f"[uniprot] Page {page}, fetched={len(all_records)}")

            response = self.session.get(
                url,
                params=params if page == 1 and not resume_cursor else None,
                timeout=60,
            )
            response.raise_for_status()

            data = response.json()
            results = data.get("results", [])
            if not results:
                break

            all_records.extend(results)

            # Save cursor after each page so interrupted runs can resume
            next_url = self._parse_link_next(response.headers.get("Link", ""))
            self.save_manifest(last_cursor=next_url, last_run_status="in_progress")

            if not next_url:
                break

            url = next_url
            params = None  # Subsequent pages: URL is self-contained
            time.sleep(_UNIPROT_DELAY)

        logger.info(f"[uniprot] Fetched {len(all_records)} proteins in {page} pages")
        return all_records[:max_results]

    @staticmethod
    def _parse_link_next(link_header: str) -> Optional[str]:
        """Extract the `next` URL from an HTTP Link header.

        Example header value:
            <https://rest.uniprot.org/uniprotkb/search?cursor=xyz&...>; rel="next"
        """
        if not link_header:
            return None
        match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
        return match.group(1) if match else None
