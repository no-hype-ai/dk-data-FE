"""Cochrane Library Systematic Reviews Fetcher.

Feature: 011-datasource-integration
Task: T064-T066 — Cochrane systematic reviews

Fetches Cochrane systematic reviews from the PubMed/NCBI E-Utilities API.
The Cochrane Library website uses Cloudflare antibot protection, blocking
programmatic access. Since all Cochrane Database of Systematic Reviews
(CDSR) articles are indexed in PubMed, we use PubMed as a reliable proxy.

Source: https://pubmed.ncbi.nlm.nih.gov/?term=Cochrane+Database+Syst+Rev
API: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/
"""

import hashlib
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Max records per fetch run
MAX_RECORDS = 2000

# NCBI rate limit: 3 requests per second (10 with API key)
REQUEST_DELAY = 0.35

# PubMed E-Utilities endpoints
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


class CochraneFetcher(BaseFetcher):
    """Fetcher for Cochrane Library systematic reviews via PubMed."""

    SOURCE_NAME = "cochrane"
    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    # Page size for search results
    PAGE_SIZE = 50

    def __init__(self, data_dir: Optional[str] = None):
        """Initialize the Cochrane fetcher."""
        super().__init__(data_dir)

        self.session.headers.update({
            "Accept": "application/xml, application/json",
            "User-Agent": "DK-Data-Platform/1.0 (Cochrane Research Integration)",
        })

    def get_latest_url(self) -> str:
        """Get the PubMed search API URL."""
        return ESEARCH_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch Cochrane systematic reviews from PubMed.

        Keyword Args:
            search_terms: List of drug names to search (default: from DB).
            max_records: Maximum records to fetch (default: 2000).
            days_back: Number of days to look back (default: 90).

        Returns:
            Dict with status, records, hash, error.
        """
        search_terms = kwargs.get("search_terms")
        max_records = kwargs.get("max_records", MAX_RECORDS)
        days_back = kwargs.get("days_back", 90)

        try:
            if not search_terms:
                search_terms = self._load_search_terms()

            if not search_terms:
                search_terms = [
                    "dupilumab",
                    "semaglutide",
                    "pembrolizumab",
                    "adalimumab",
                    "nivolumab",
                ]
                logger.info(
                    "No search terms from DB; using %d default pharma terms",
                    len(search_terms),
                )

            logger.info(
                "Fetching Cochrane reviews via PubMed (terms=%d, days_back=%d)",
                len(search_terms), days_back,
            )

            all_records: List[Dict[str, Any]] = []
            seen_ids: set = set()

            for term in search_terms:
                if len(all_records) >= max_records:
                    break

                records = self._search_reviews(
                    term,
                    days_back=days_back,
                    max_records=max_records - len(all_records),
                )

                for rec in records:
                    review_id = rec.get("review_id")
                    if review_id and review_id not in seen_ids:
                        seen_ids.add(review_id)
                        all_records.append(rec)

            content_hash = hashlib.md5(
                str(sorted(seen_ids)).encode()
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
            logger.exception("Failed to fetch Cochrane data: %s", e)
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
    # Search via PubMed E-Utilities
    # ------------------------------------------------------------------

    def _search_reviews(
        self,
        term: str,
        *,
        days_back: int = 90,
        max_records: int = 2000,
    ) -> List[Dict[str, Any]]:
        """Search PubMed for Cochrane reviews matching a drug term."""
        # Build the PubMed query: Cochrane journal + drug term + date filter
        query = f'"{term}" AND "Cochrane Database Syst Rev"[journal]'

        try:
            # Step 1: ESearch to get PMIDs
            search_params = {
                "db": "pubmed",
                "term": query,
                "retmax": min(max_records, self.PAGE_SIZE),
                "retmode": "json",
                "datetype": "pdat",
                "reldate": days_back,
            }

            resp = self.session.get(ESEARCH_URL, params=search_params, timeout=30)
            resp.raise_for_status()
            search_data = resp.json()

            id_list = search_data.get("esearchresult", {}).get("idlist", [])
            if not id_list:
                return []

            time.sleep(REQUEST_DELAY)

            # Step 2: EFetch to get article details
            records = self._fetch_article_details(id_list, term)
            return records

        except Exception as e:
            logger.warning(
                "PubMed search failed for Cochrane term '%s': %s", term, e
            )
            return []

    def _fetch_article_details(
        self, pmids: List[str], search_term: str
    ) -> List[Dict[str, Any]]:
        """Fetch full article details from PubMed for a list of PMIDs."""
        records: List[Dict[str, Any]] = []

        # Fetch in batches of 50
        for i in range(0, len(pmids), self.PAGE_SIZE):
            batch = pmids[i:i + self.PAGE_SIZE]

            try:
                fetch_params = {
                    "db": "pubmed",
                    "id": ",".join(batch),
                    "retmode": "xml",
                    "rettype": "abstract",
                }

                resp = self.session.get(EFETCH_URL, params=fetch_params, timeout=30)
                resp.raise_for_status()

                # Parse XML response
                root = ElementTree.fromstring(resp.content)

                for article in root.findall(".//PubmedArticle"):
                    record = self._parse_pubmed_article(article, search_term)
                    if record:
                        records.append(record)

                time.sleep(REQUEST_DELAY)

            except Exception as e:
                logger.warning("PubMed EFetch failed for batch: %s", e)

        return records

    @staticmethod
    def _parse_pubmed_article(
        article: ElementTree.Element, search_term: str
    ) -> Optional[Dict[str, Any]]:
        """Parse a PubmedArticle XML element into a Cochrane review record."""
        medline = article.find(".//MedlineCitation")
        if medline is None:
            return None

        pmid_el = medline.find("PMID")
        if pmid_el is None or not pmid_el.text:
            return None

        review_id = f"pmid-{pmid_el.text}"

        # Title
        title_el = medline.find(".//ArticleTitle")
        title = title_el.text if title_el is not None and title_el.text else None

        # Authors
        author_list = medline.findall(".//Author")
        authors_parts = []
        for author in author_list:
            last = author.findtext("LastName", "")
            initials = author.findtext("Initials", "")
            if last:
                authors_parts.append(f"{last} {initials}".strip())
        authors = "; ".join(authors_parts) if authors_parts else None

        # Abstract
        abstract_parts = []
        for abstract_text in medline.findall(".//AbstractText"):
            label = abstract_text.get("Label", "")
            text = abstract_text.text or ""
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
        abstract = " ".join(abstract_parts) if abstract_parts else None

        # Publication date
        pub_date = None
        date_el = medline.find(".//PubDate")
        if date_el is not None:
            year = date_el.findtext("Year", "")
            month = date_el.findtext("Month", "01")
            day = date_el.findtext("Day", "01")
            if year:
                # Convert month name to number if needed
                try:
                    month_num = datetime.strptime(month, "%b").month if not month.isdigit() else int(month)
                    pub_date = f"{year}-{month_num:02d}-{int(day):02d}"
                except (ValueError, TypeError):
                    pub_date = f"{year}-01-01"

        # DOI
        doi = None
        for id_el in article.findall(".//ArticleId"):
            if id_el.get("IdType") == "doi":
                doi = id_el.text

        # MeSH terms as conditions/interventions
        mesh_terms = []
        for mesh in medline.findall(".//MeshHeading/DescriptorName"):
            if mesh.text:
                mesh_terms.append(mesh.text)

        return {
            "review_id": review_id,
            "title": title,
            "authors": authors,
            "abstract": abstract[:2000] if abstract else None,
            "publication_date": pub_date,
            "review_type": "systematic_review",
            "interventions": [search_term] if search_term else None,
            "conditions": mesh_terms[:10] if mesh_terms else None,
            "conclusions": None,
            "doi": doi,
        }

    # ------------------------------------------------------------------
    # Search terms from database
    # ------------------------------------------------------------------

    def _load_search_terms(self) -> List[str]:
        """Load active drug_name search terms from meta.ops_ci_search_terms."""
        try:
            from ..utils.database import get_connection

            terms: List[str] = []
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT term_value
                        FROM meta.ops_ci_search_terms
                        WHERE term_type = 'drug_name'
                          AND is_active = TRUE
                        ORDER BY term_value
                        """
                    )
                    for row in cur.fetchall():
                        terms.append(row[0])

            logger.info("Loaded %d drug_name terms from meta.ops_ci_search_terms", len(terms))
            return terms

        except Exception as e:
            logger.warning("Could not load search terms from DB: %s", e)
            return []
