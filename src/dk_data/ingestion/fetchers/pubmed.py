"""PubMed / NCBI E-utilities Data Fetcher.

Feature: 011-datasource-integration
Task: PubMed CI source integration

Fetches pharmaceutical/clinical literature from PubMed using NCBI
E-utilities (esearch + efetch).  Supports optional NCBI_API_KEY for
higher rate limits (10 req/s vs 3 req/s).

Self-loading: streams records directly to DB in batches of FLUSH_SIZE
(default 200) with checkpoint/resume. For large date windows (e.g.,
10yr backfill), the fetcher processes year-by-year to avoid NCBI
connection drops on very large result sets.

Source: https://www.ncbi.nlm.nih.gov/books/NBK25497/
"""

import hashlib
import logging
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base import BaseFetcher
from ..utils.checkpoint import clear_checkpoint, load_checkpoint, save_checkpoint
from ..sources.pubmed import load_pubmed_data

logger = logging.getLogger(__name__)

# Flush to DB every FLUSH_SIZE records to stay within 512Mi pod limit
FLUSH_SIZE = 200
# Process year-by-year for windows larger than this (avoids NCBI disconnects)
YEAR_CHUNK_THRESHOLD = 365


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
        """Fetch PubMed articles with streaming DB insert and checkpoint/resume.

        For large date windows (> 1 year), processes year-by-year to avoid
        NCBI connection drops. Each batch of FLUSH_SIZE records is inserted
        to DB immediately, keeping memory bounded.

        Keyword Args:
            query: Custom PubMed search query. Defaults to pharma terms.
            days_back: Number of days to look back. Defaults to 30.
            retmax: Maximum PMIDs per esearch page. Defaults to 500.

        Returns:
            Dict with keys: status, records (always []), record_count, hash.
            records is always [] — data is streamed directly to DB.
        """
        query: str = kwargs.get("query", self.DEFAULT_SEARCH_TERMS)
        days_back: int = kwargs.get("days_back", 30)
        retmax: int = min(kwargs.get("retmax", 500), self.MAX_BATCH_SIZE)

        try:
            total_inserted = self._fetch_and_load(
                query=query,
                days_back=days_back,
                retmax=retmax,
            )

            content_hash = hashlib.md5(
                f"pubmed:{days_back}:{total_inserted}".encode()
            ).hexdigest()

            clear_checkpoint(self.SOURCE_NAME)

            result: Dict[str, Any] = {
                "status": "success",
                "records": [],
                "record_count": total_inserted,
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": total_inserted})
            return result

        except Exception as e:
            logger.exception("PubMed fetch failed: %s", e)
            result = {
                "status": "failed",
                "records": [],
                "hash": None,
                "error": str(e),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_and_load(self, query: str, days_back: int, retmax: int) -> int:
        """Fetch and stream PubMed articles to DB with checkpoint/resume.

        For windows > YEAR_CHUNK_THRESHOLD days, splits into year-by-year
        chunks to avoid NCBI connection drops on large result sets.

        Returns total records inserted.
        """
        # Resume from checkpoint
        cp = load_checkpoint(self.SOURCE_NAME)
        total_inserted: int = cp.get("total_inserted", 0) if cp else 0
        completed_years: list = cp.get("completed_years", []) if cp else []

        if cp:
            logger.info(
                "PubMed: resuming from checkpoint, %d already inserted, %d years done",
                total_inserted, len(completed_years),
            )

        # For large windows, split into yearly chunks
        if days_back > YEAR_CHUNK_THRESHOLD:
            now = datetime.utcnow()
            start_date = now - timedelta(days=days_back)
            current_year = now.year
            start_year = start_date.year

            for year in range(start_year, current_year + 1):
                if year in completed_years:
                    logger.info("PubMed: skipping year %d (already complete)", year)
                    continue

                year_start = max(
                    datetime(year, 1, 1),
                    start_date,
                )
                year_end = min(
                    datetime(year, 12, 31),
                    now,
                )
                year_days = (year_end - year_start).days + 1

                logger.info(
                    "PubMed: fetching year %d (%d days)",
                    year, year_days,
                )

                year_count = self._fetch_year(
                    query=query,
                    days_back=year_days,
                    retmax=retmax,
                    min_date=year_start.strftime("%Y/%m/%d"),
                    max_date=year_end.strftime("%Y/%m/%d"),
                )
                total_inserted += year_count
                completed_years.append(year)

                save_checkpoint(self.SOURCE_NAME, {
                    "total_inserted": total_inserted,
                    "completed_years": completed_years,
                })
                logger.info(
                    "PubMed: year %d done (%d records), total=%d",
                    year, year_count, total_inserted,
                )
        else:
            # Short window — single pass
            count = self._fetch_year(
                query=query,
                days_back=days_back,
                retmax=retmax,
            )
            total_inserted += count

        logger.info("PubMed: complete — %d total inserted", total_inserted)
        return total_inserted

    def _fetch_year(
        self,
        query: str,
        days_back: int,
        retmax: int,
        min_date: Optional[str] = None,
        max_date: Optional[str] = None,
    ) -> int:
        """Fetch one year (or date range) of PubMed articles, streaming to DB.

        Returns number of records inserted.
        """
        # Step 1: esearch to get PMIDs
        pmids = self._esearch(
            query,
            days_back=days_back,
            retmax=retmax,
            min_date=min_date,
            max_date=max_date,
        )

        if not pmids:
            return 0

        logger.info("PubMed esearch: %d PMIDs for window", len(pmids))

        # Step 2: efetch in batches, flush to DB every FLUSH_SIZE
        inserted = 0
        record_buffer: List[Dict[str, Any]] = []

        for i in range(0, len(pmids), FLUSH_SIZE):
            batch_pmids = pmids[i: i + FLUSH_SIZE]
            records = self._efetch(batch_pmids)
            record_buffer.extend(records)

            # Flush to DB
            if record_buffer:
                result = load_pubmed_data(record_buffer)
                inserted += result.get("records_inserted", 0)
                record_buffer = []

            self._rate_sleep()

        # Flush remaining
        if record_buffer:
            result = load_pubmed_data(record_buffer)
            inserted += result.get("records_inserted", 0)

        return inserted

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
        min_date: Optional[str] = None,
        max_date: Optional[str] = None,
    ) -> List[str]:
        """Search PubMed and return a list of PMIDs.

        Uses either reldate (relative date) or mindate/maxdate (absolute range).
        Handles pagination via retstart. No max_results cap — fetches all matching PMIDs.
        """
        url = f"{self.BASE_URL}/esearch.fcgi"
        all_pmids: List[str] = []
        retstart = 0

        while True:
            params = {
                **self._common_params(),
                "term": query,
                "datetype": "edat",
                "retmax": str(retmax),
                "retstart": str(retstart),
                "retmode": "xml",
                "usehistory": "n",
            }

            # Use absolute date range if provided, otherwise relative
            if min_date and max_date:
                params["mindate"] = min_date
                params["maxdate"] = max_date
            else:
                params["reldate"] = str(days_back)

            logger.debug("esearch retstart=%d", retstart)
            response = self.session.get(url, params=params, timeout=60)
            response.raise_for_status()

            root = ET.fromstring(response.content)

            error_list = root.find("ErrorList")
            if error_list is not None:
                errors = [e.text for e in error_list]
                logger.warning("esearch returned errors: %s", errors)

            id_list = root.find("IdList")
            if id_list is None:
                break

            batch_ids = [id_elem.text for id_elem in id_list.findall("Id") if id_elem.text]
            if not batch_ids:
                break

            all_pmids.extend(batch_ids)

            count_elem = root.find("Count")
            total_count = int(count_elem.text) if count_elem is not None and count_elem.text else 0

            retstart += retmax

            if retstart >= total_count:
                break

            self._rate_sleep()

        return all_pmids

    # -- efetch --------------------------------------------------------

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
