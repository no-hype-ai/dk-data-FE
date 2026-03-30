"""PubMed / NCBI E-utilities Data Fetcher.

Feature: 011-datasource-integration
Task: PubMed CI source integration

Fetches recent pharmaceutical/clinical literature from PubMed using
NCBI E-utilities (esearch + efetch).  Supports optional NCBI_API_KEY
for higher rate limits (10 req/s vs 3 req/s).

Source: https://www.ncbi.nlm.nih.gov/books/NBK25497/
"""

import hashlib
import logging
import os
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class PubMedFetcher(BaseFetcher):
    """Fetcher for PubMed literature via NCBI E-utilities."""

    SOURCE_NAME = "pubmed"
    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    # Reasonable upper bound per batch request
    MAX_BATCH_SIZE = 10000

    # Default search terms for pharma / clinical interest
    DEFAULT_SEARCH_TERMS = (
        "(pharmaceutical[MeSH] OR drug therapy[MeSH] OR clinical trial[pt])"
    )

    def __init__(self, data_dir: Optional[str] = None):
        """Initialize the PubMed fetcher.

        Reads NCBI_API_KEY from the environment (optional).
        """
        super().__init__(data_dir)
        self.api_key: Optional[str] = os.environ.get("NCBI_API_KEY")
        if self.api_key:
            logger.info("NCBI API key detected; using authenticated rate limit")
        else:
            logger.info(
                "No NCBI_API_KEY set; using unauthenticated rate limit (3 req/s)"
            )

    # ------------------------------------------------------------------
    # BaseFetcher abstract interface
    # ------------------------------------------------------------------

    def get_latest_url(self) -> str:
        """Return the esearch endpoint URL."""
        return f"{self.BASE_URL}/esearch.fcgi"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch recent PubMed articles.

        Keyword Args:
            query: Custom PubMed search query. Defaults to pharma terms.
            days_back: Number of days to look back. Defaults to 1.
            retmax: Maximum records per E-utilities batch. Defaults to 500.
            max_records: Hard cap on total results. Defaults to 10000.

        Returns:
            Dict with keys: status, records, record_count, hash, error (on failure).
        """
        query: str = kwargs.get("query", self.DEFAULT_SEARCH_TERMS)
        days_back: int = kwargs.get("days_back", 1)
        retmax: int = min(kwargs.get("retmax", 500), self.MAX_BATCH_SIZE)
        max_results: int = kwargs.get("max_records", kwargs.get("max_results", self.MAX_BATCH_SIZE))

        try:
            # Step 1: esearch to get PMIDs
            pmids = self._esearch(query, days_back=days_back, retmax=retmax, max_results=max_results)

            if not pmids:
                result: Dict[str, Any] = {
                    "status": "success",
                    "records": [],
                    "record_count": 0,
                    "hash": None,
                    "message": "No articles found for the given query/date range",
                }
                self.log_fetch_result(result)
                return result

            logger.info(f"esearch returned {len(pmids)} PMIDs")

            # Step 2: efetch to retrieve article details in batches
            records = self._efetch_batched(pmids, batch_size=200)

            # Compute a deterministic hash over sorted PMIDs for change detection
            content_hash = hashlib.md5(
                ",".join(sorted(pmids)).encode()
            ).hexdigest()

            result = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
            }
            self.log_fetch_result({**result, "records": len(records)})
            return result

        except Exception as e:
            logger.exception(f"PubMed fetch failed: {e}")
            result = {
                "status": "failed",
                "records": [],
                "hash": None,
                "error": str(e),
            }
            self.log_fetch_result(result)
            return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _common_params(self) -> Dict[str, str]:
        """Return params common to every E-utilities request."""
        params: Dict[str, str] = {"db": "pubmed"}
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    def _rate_sleep(self) -> None:
        """Sleep to respect NCBI rate limits."""
        # Authenticated: 10 req/s, unauthenticated: 3 req/s
        delay = 0.11 if self.api_key else 0.34
        time.sleep(delay)

    # -- esearch -------------------------------------------------------

    def _esearch(
        self,
        query: str,
        days_back: int = 1,
        retmax: int = 500,
        max_results: int = 10000,
    ) -> List[str]:
        """Search PubMed and return a list of PMIDs.

        Uses reldate (relative date) to restrict to recent articles.
        Handles pagination via retstart.
        """
        url = f"{self.BASE_URL}/esearch.fcgi"
        all_pmids: List[str] = []
        retstart = 0

        while True:
            params = {
                **self._common_params(),
                "term": query,
                "reldate": str(days_back),
                "datetype": "edat",  # Entrez date (date added to PubMed)
                "retmax": str(retmax),
                "retstart": str(retstart),
                "retmode": "xml",
                "usehistory": "n",
            }

            logger.debug(f"esearch retstart={retstart}")
            response = self.session.get(url, params=params, timeout=60)
            response.raise_for_status()

            root = ET.fromstring(response.content)

            # Check for errors in the XML response
            error_list = root.find("ErrorList")
            if error_list is not None:
                errors = [e.text for e in error_list]
                logger.warning(f"esearch returned errors: {errors}")

            id_list = root.find("IdList")
            if id_list is None:
                break

            batch_ids = [id_elem.text for id_elem in id_list.findall("Id") if id_elem.text]
            if not batch_ids:
                break

            all_pmids.extend(batch_ids)

            # Check total count
            count_elem = root.find("Count")
            total_count = int(count_elem.text) if count_elem is not None and count_elem.text else 0

            retstart += retmax

            # Stop conditions
            if retstart >= total_count:
                break
            if len(all_pmids) >= max_results:
                all_pmids = all_pmids[:max_results]
                break

            self._rate_sleep()

        return all_pmids

    # -- efetch --------------------------------------------------------

    def _efetch_batched(
        self,
        pmids: List[str],
        batch_size: int = 200,
    ) -> List[Dict[str, Any]]:
        """Fetch article details for a list of PMIDs in batches."""
        all_records: List[Dict[str, Any]] = []

        for i in range(0, len(pmids), batch_size):
            batch = pmids[i : i + batch_size]
            logger.debug(f"efetch batch {i // batch_size + 1}: {len(batch)} PMIDs")

            records = self._efetch(batch)
            all_records.extend(records)
            self._rate_sleep()

        logger.info(f"efetch returned {len(all_records)} article records total")
        return all_records

    def _efetch(self, pmids: List[str]) -> List[Dict[str, Any]]:
        """Fetch full article records for a batch of PMIDs.

        Uses POST to avoid 414 URI Too Long errors with large ID lists.
        """
        url = f"{self.BASE_URL}/efetch.fcgi"
        data = {
            **self._common_params(),
            "id": ",".join(pmids),
            "rettype": "xml",
            "retmode": "xml",
        }

        response = self.session.post(url, data=data, timeout=120)
        response.raise_for_status()

        return self._parse_efetch_xml(response.content)

    # -- XML parsing ---------------------------------------------------

    def _parse_efetch_xml(self, xml_content: bytes) -> List[Dict[str, Any]]:
        """Parse PubMed efetch XML into a list of record dicts."""
        records: List[Dict[str, Any]] = []

        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            logger.error(f"Failed to parse efetch XML: {e}")
            return records

        for article_elem in root.findall(".//PubmedArticle"):
            try:
                record = self._parse_article(article_elem)
                if record:
                    records.append(record)
            except Exception as e:
                pmid = self._safe_text(
                    article_elem, ".//MedlineCitation/PMID"
                )
                logger.warning(f"Failed to parse article PMID={pmid}: {e}")

        return records

    def _parse_article(self, article_elem: ET.Element) -> Optional[Dict[str, Any]]:
        """Parse a single <PubmedArticle> element into a record dict."""
        citation = article_elem.find("MedlineCitation")
        if citation is None:
            return None

        pmid = self._safe_text(citation, "PMID")
        if not pmid:
            return None

        article = citation.find("Article")
        if article is None:
            return None

        # Title
        title = self._safe_text(article, "ArticleTitle") or ""

        # Abstract — concatenate all AbstractText sections
        abstract_parts: List[str] = []
        abstract_elem = article.find("Abstract")
        if abstract_elem is not None:
            for text_elem in abstract_elem.findall("AbstractText"):
                label = text_elem.get("Label", "")
                # itertext() captures mixed-content (e.g. <i> tags inside text)
                text = "".join(text_elem.itertext()).strip()
                if label:
                    abstract_parts.append(f"{label}: {text}")
                else:
                    abstract_parts.append(text)
        abstract = "\n".join(abstract_parts) if abstract_parts else None

        # Authors
        authors = self._parse_authors(article)

        # Journal
        journal_elem = article.find("Journal")
        journal = self._safe_text(journal_elem, "Title") if journal_elem is not None else None

        # Publication date
        pub_date = self._parse_pub_date(article)

        # MeSH terms
        mesh_terms = self._parse_mesh_terms(citation)

        # DOI
        doi = self._parse_doi(article_elem)

        # Publication types
        pub_types = [
            pt.text
            for pt in article.findall("PublicationTypeList/PublicationType")
            if pt.text
        ]

        # Keywords
        keywords = [
            kw.text
            for kw in citation.findall("KeywordList/Keyword")
            if kw.text
        ]

        return {
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "journal": journal,
            "publication_date": pub_date,
            "mesh_terms": mesh_terms,
            "doi": doi,
            "publication_types": pub_types,
            "keywords": keywords,
        }

    def _parse_authors(self, article: ET.Element) -> List[Dict[str, str]]:
        """Extract author list from an <Article> element."""
        authors: List[Dict[str, str]] = []
        for author_elem in article.findall("AuthorList/Author"):
            last = self._safe_text(author_elem, "LastName") or ""
            fore = self._safe_text(author_elem, "ForeName") or ""
            initials = self._safe_text(author_elem, "Initials") or ""
            affiliation = self._safe_text(
                author_elem, "AffiliationInfo/Affiliation"
            ) or ""

            if last or fore:
                authors.append(
                    {
                        "last_name": last,
                        "fore_name": fore,
                        "initials": initials,
                        "affiliation": affiliation,
                    }
                )
        return authors

    def _parse_pub_date(self, article: ET.Element) -> Optional[str]:
        """Extract publication date as ISO string (YYYY-MM-DD or partial)."""
        # Try Journal > JournalIssue > PubDate first
        pub_date = article.find("Journal/JournalIssue/PubDate")
        if pub_date is None:
            pub_date = article.find("ArticleDate")
        if pub_date is None:
            return None

        year = self._safe_text(pub_date, "Year")
        month = self._safe_text(pub_date, "Month")
        day = self._safe_text(pub_date, "Day")

        if not year:
            # Try MedlineDate (e.g., "2024 Jan-Feb")
            medline_date = self._safe_text(pub_date, "MedlineDate")
            if medline_date:
                return medline_date[:10]  # best-effort truncation
            return None

        # Convert month name to number if needed
        month_num = self._month_to_num(month) if month else None

        if year and month_num and day:
            return f"{year}-{month_num:02d}-{int(day):02d}"
        elif year and month_num:
            return f"{year}-{month_num:02d}-01"
        else:
            return f"{year}-01-01"

    def _parse_mesh_terms(self, citation: ET.Element) -> List[str]:
        """Extract MeSH headings from a <MedlineCitation> element."""
        terms: List[str] = []
        for mesh in citation.findall("MeshHeadingList/MeshHeading"):
            descriptor = mesh.find("DescriptorName")
            if descriptor is not None and descriptor.text:
                terms.append(descriptor.text)
        return terms

    def _parse_doi(self, article_elem: ET.Element) -> Optional[str]:
        """Extract DOI from ELocationID or ArticleIdList."""
        # Try ELocationID first
        for eloc in article_elem.findall(
            ".//Article/ELocationID"
        ):
            if eloc.get("EIdType") == "doi" and eloc.text:
                return eloc.text

        # Fallback to ArticleIdList in PubmedData
        for aid in article_elem.findall(
            ".//PubmedData/ArticleIdList/ArticleId"
        ):
            if aid.get("IdType") == "doi" and aid.text:
                return aid.text

        return None

    @staticmethod
    def _safe_text(parent: Optional[ET.Element], path: str) -> Optional[str]:
        """Safely extract text from an XML sub-element."""
        if parent is None:
            return None
        elem = parent.find(path)
        if elem is not None and elem.text:
            return elem.text.strip()
        return None

    @staticmethod
    def _month_to_num(month: Optional[str]) -> Optional[int]:
        """Convert a month name or abbreviation to a number."""
        if month is None:
            return None

        month_lower = month.strip().lower()

        # If already numeric
        if month_lower.isdigit():
            num = int(month_lower)
            return num if 1 <= num <= 12 else None

        month_map = {
            "jan": 1, "january": 1,
            "feb": 2, "february": 2,
            "mar": 3, "march": 3,
            "apr": 4, "april": 4,
            "may": 5,
            "jun": 6, "june": 6,
            "jul": 7, "july": 7,
            "aug": 8, "august": 8,
            "sep": 9, "september": 9,
            "oct": 10, "october": 10,
            "nov": 11, "november": 11,
            "dec": 12, "december": 12,
        }

        return month_map.get(month_lower)
