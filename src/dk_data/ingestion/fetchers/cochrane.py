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

import calendar
import hashlib
import json
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

            # When no molecule-specific search terms are available, fetch ALL
            # Cochrane systematic reviews by using just the journal filter
            # (no drug-name term restriction). This enables a full backfill
            # without requiring silver-layer molecule data to exist first.
            use_all_journal = not search_terms
            if use_all_journal:
                search_terms = [None]  # type: ignore[list-item]

            logger.info(
                "Fetching Cochrane reviews via PubMed (%s, days_back=%d)",
                f"terms={len(search_terms)}" if not use_all_journal else "all-journal",
                days_back,
            )

            all_records: List[Dict[str, Any]] = []
            seen_pmids: set = set()  # tracks raw PMID strings for dedup

            for term in search_terms:
                if len(all_records) >= max_records:
                    break

                pmids = self._search_pmids(
                    term,
                    days_back=days_back,
                    max_results=max_records - len(all_records),
                )

                # Filter to PMIDs not yet fetched (dedup by PMID, not review_id)
                new_pmids = [p for p in pmids if p not in seen_pmids]
                if not new_pmids:
                    continue

                records = self._fetch_summaries(new_pmids, term)
                for rec in records:
                    seen_pmids.add(rec["pmid"])  # track by PMID for dedup
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
        term: Optional[str],
        *,
        days_back: int = 90,
        max_results: int = 500,
    ) -> List[str]:
        """Search PubMed for Cochrane CDSR PMIDs.

        When term is None, fetches ALL Cochrane CDSR articles (journal-only
        filter). When term is provided, restricts to Title/Abstract matches.
        """
        date_from = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y/%m/%d")
        date_to   = datetime.utcnow().strftime("%Y/%m/%d")

        # journal-only when no term (full backfill mode)
        if term is None:
            query = '"Cochrane Database Syst Rev"[Journal]'
        else:
            query = (
                f'"{term}"[Title/Abstract] '
                f'AND "Cochrane Database Syst Rev"[Journal]'
            )

        params = {
            "db": "pubmed",
            "term": query,
            "retmax": str(min(max_results, 10000)),
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

        # Authors — stored as JSONB array in mol_raw.cochrane_reviews.
        # Return as a JSON array string so psycopg2's text→JSONB assignment
        # cast succeeds. Plain semicolon strings are not valid JSON and would
        # cause "invalid input syntax for type json" at insert time.
        authors_raw = item.get("authors", [])
        if isinstance(authors_raw, list):
            authors_list = [a.get("name", "") for a in authors_raw if a.get("name")]
            authors = json.dumps(authors_list) if authors_list else None
        else:
            authors = None

        # Publication date — PubMed pubdate is NOT ISO 8601.
        # Formats seen: "2026 Mar 15", "2026 Mar", "2026", "2026-03-15".
        # Pydantic Optional[date] uses date.fromisoformat() which only accepts
        # ISO format; "2026 Mar 1" (from [:10]) raises ValidationError every time.
        pub_date = self._parse_pubmed_date(
            item.get("pubdate") or item.get("epubdate") or ""
        )

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
    # Date parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_pubmed_date(pubdate: str) -> Optional[str]:
        """Parse PubMed pubdate string to ISO YYYY-MM-DD.

        PubMed returns dates as "2026 Mar 15", "2026 Mar", or "2026".
        Pydantic Optional[date] requires ISO 8601 — anything else raises
        ValidationError and silently drops the record in the loader.
        """
        if not pubdate:
            return None
        pubdate = pubdate.strip()
        # Already ISO format (YYYY-MM-DD or YYYY-MM)
        if "-" in pubdate:
            parts = pubdate.split("-")
            if len(parts) >= 3:
                return f"{parts[0]}-{parts[1]}-{parts[2]}"
            if len(parts) == 2:
                return f"{parts[0]}-{parts[1]}-01"
            return f"{parts[0]}-01-01"
        # PubMed space-separated: "2026 Mar 15", "2026 Mar", "2026"
        parts = pubdate.split()
        try:
            if len(parts) == 1:
                return f"{parts[0]}-01-01"
            month_num = list(calendar.month_abbr).index(parts[1].capitalize())
            if len(parts) == 2:
                return f"{parts[0]}-{month_num:02d}-01"
            return f"{parts[0]}-{month_num:02d}-{int(parts[2]):02d}"
        except (ValueError, IndexError):
            return None

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
