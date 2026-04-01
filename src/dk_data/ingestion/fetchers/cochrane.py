"""Cochrane Library Systematic Reviews Fetcher.

Feature: 011-datasource-integration
Task: T064-T066 — Cochrane systematic reviews

Fetches Cochrane systematic reviews via PubMed eUtils API.
The Cochrane Library's own search API (cochranelibrary.com/api/search)
now returns 404/419 (Cloudflare-blocked, #189). PubMed indexes all
Cochrane Database of Systematic Reviews (CDSR) articles with full
metadata and is accessible without authentication.

Source: https://pubmed.ncbi.nlm.nih.gov (Cochrane Reviews filter)
API: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/
"""

import hashlib
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Max records per fetch run
MAX_RECORDS = 2000

# Rate limit: NCBI allows 3 req/s without API key, 10/s with
REQUEST_DELAY = 0.4

# PubMed eUtils base URL
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

# Cochrane Database of Systematic Reviews journal NLM ID
COCHRANE_JOURNAL = "Cochrane Database Syst Rev"

# Number of PMIDs to fetch per eSummary batch
BATCH_SIZE = 50


class CochraneFetcher(BaseFetcher):
    """Fetcher for Cochrane systematic reviews via PubMed eUtils."""

    SOURCE_NAME = "cochrane"
    BASE_URL = ESEARCH_URL

    def __init__(self, data_dir: Optional[str] = None):
        """Initialize the Cochrane fetcher."""
        super().__init__(data_dir)
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "DK-Data-Platform/1.0 (research; contact: ops@datakinetic.com)",
        })

    def get_latest_url(self) -> str:
        """Get the PubMed eSearch URL used for Cochrane queries."""
        return ESEARCH_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch systematic reviews via PubMed for Cochrane CDSR articles.

        Keyword Args:
            search_terms: List of drug names to search (default: from DB).
            max_records: Maximum records to fetch (default: 2000).
            days_back: Number of days to look back (default: 90).

        Returns:
            Dict with status, records, record_count, hash, error.
        """
        search_terms = kwargs.get("search_terms")
        max_records = kwargs.get("max_records", MAX_RECORDS)
        days_back = kwargs.get("days_back", 90)

        try:
            if not search_terms:
                search_terms = self._load_search_terms()

            if not search_terms:
                search_terms = ["pharmaceutical intervention"]

            logger.info(
                "Fetching Cochrane reviews via PubMed (terms=%d, days_back=%d)",
                len(search_terms), days_back,
            )

            all_records: List[Dict[str, Any]] = []
            seen_pmids: set = set()

            for term in search_terms:
                if len(all_records) >= max_records:
                    break

                pmids = self._search_pmids(
                    term,
                    days_back=days_back,
                    max_results=max_records - len(all_records),
                )

                new_pmids = [p for p in pmids if p not in seen_pmids]
                if not new_pmids:
                    continue

                records = self._fetch_summaries(new_pmids, term)
                for rec in records:
                    seen_pmids.add(rec["review_id"])
                    all_records.append(rec)

                time.sleep(REQUEST_DELAY)

            content_hash = hashlib.md5(
                str(sorted(seen_pmids)).encode()
            ).hexdigest()

            result = {
                "status": "success",
                "records": all_records,
                "record_count": len(all_records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(all_records)})
            return result

        except Exception as e:
            logger.exception("Failed to fetch Cochrane data via PubMed: %s", e)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(e),
            }
            self.log_fetch_result(result)
            return result

    # ------------------------------------------------------------------
    # PubMed eSearch — get PMIDs for Cochrane reviews
    # ------------------------------------------------------------------

    def _search_pmids(
        self,
        term: str,
        *,
        days_back: int = 90,
        max_results: int = 500,
    ) -> List[str]:
        """Search PubMed for Cochrane CDSR PMIDs matching a drug term."""
        date_from = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y/%m/%d")
        date_to   = datetime.utcnow().strftime("%Y/%m/%d")

        # Filter to Cochrane Database of Systematic Reviews
        query = (
            f'"{term}"[Title/Abstract] '
            f'AND "Cochrane Database Syst Rev"[Journal]'
        )

        params = {
            "db": "pubmed",
            "term": query,
            "retmax": str(min(max_results, 500)),
            "retmode": "json",
            "datetype": "pdat",
            "mindate": date_from,
            "maxdate": date_to,
        }

        try:
            data = self.fetch_json(ESEARCH_URL, params=params)
            ids = data.get("esearchresult", {}).get("idlist", [])
            logger.debug("PubMed eSearch '%s' → %d PMIDs", term, len(ids))
            return ids
        except Exception as e:
            logger.warning("PubMed eSearch failed for '%s': %s", term, e)
            return []

    # ------------------------------------------------------------------
    # PubMed eSummary — fetch metadata for PMIDs
    # ------------------------------------------------------------------

    def _fetch_summaries(
        self, pmids: List[str], search_term: str
    ) -> List[Dict[str, Any]]:
        """Fetch eSummary records for a list of PMIDs."""
        records: List[Dict[str, Any]] = []

        for i in range(0, len(pmids), BATCH_SIZE):
            batch = pmids[i : i + BATCH_SIZE]
            params = {
                "db": "pubmed",
                "id": ",".join(batch),
                "retmode": "json",
                "version": "2.0",
            }

            try:
                data = self.fetch_json(ESUMMARY_URL, params=params)
                result_set = data.get("result", {})

                for pmid in batch:
                    item = result_set.get(pmid)
                    if not item or item.get("error"):
                        continue
                    normalized = self._normalize_summary(item, search_term)
                    if normalized:
                        records.append(normalized)

                time.sleep(REQUEST_DELAY)

            except Exception as e:
                logger.warning(
                    "PubMed eSummary failed for batch starting at %d: %s", i, e
                )

        return records

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def _normalize_summary(
        self, item: Dict[str, Any], search_term: str
    ) -> Optional[Dict[str, Any]]:
        """Normalize a PubMed eSummary record to the Cochrane raw schema."""
        pmid = item.get("uid")
        if not pmid:
            return None

        # Authors
        authors_raw = item.get("authors", [])
        if isinstance(authors_raw, list):
            authors = "; ".join(
                a.get("name", "") for a in authors_raw if a.get("name")
            )
        else:
            authors = str(authors_raw)

        # Publication date
        pub_date = item.get("pubdate") or item.get("epubdate") or ""
        if pub_date:
            pub_date = pub_date[:10]

        # DOI from article IDs
        doi = None
        for aid in item.get("articleids", []):
            if aid.get("idtype") == "doi":
                doi = aid.get("value")
                break

        # Build Cochrane review ID: prefer DOI, fall back to PMID
        review_id = doi if doi else f"pmid:{pmid}"

        return {
            "review_id": review_id,
            "title": item.get("title"),
            "authors": authors or None,
            "abstract": None,          # eSummary doesn't include abstract
            "publication_date": pub_date or None,
            "review_type": "systematic_review",
            "interventions": None,     # Not available in eSummary
            "conditions": None,        # Not available in eSummary
            "conclusions": None,       # Not available in eSummary
            "doi": doi,
            "pmid": pmid,
            "source": "pubmed_cochrane",
            "search_term": search_term,
        }

    # ------------------------------------------------------------------
    # Search terms from database
    # ------------------------------------------------------------------

    def _load_search_terms(self) -> List[str]:
        """Load active drug_name search terms from meta.ci_search_terms."""
        try:
            from ..utils.database import get_connection

            terms: List[str] = []
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT term_value
                        FROM meta.ci_search_terms
                        WHERE term_type = 'drug_name'
                          AND is_active = TRUE
                        ORDER BY term_value
                        """
                    )
                    for row in cur.fetchall():
                        terms.append(row[0])

            logger.info(
                "Loaded %d drug_name terms from meta.ci_search_terms", len(terms)
            )
            return terms

        except Exception as e:
            logger.warning("Could not load search terms from DB: %s", e)
            return []
