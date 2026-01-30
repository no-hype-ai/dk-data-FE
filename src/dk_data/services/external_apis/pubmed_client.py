"""
PubMed E-utilities API Client.

Implements T024: PubMedClient for scientific publications
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
import xml.etree.ElementTree as ET
import aiohttp
from loguru import logger

from .base_client import BaseAPIClient, APIResponse, APIClientConfig


@dataclass
class Publication:
    """Publication data structure."""
    pmid: str
    title: str
    abstract: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    journal: Optional[str] = None
    publication_date: Optional[datetime] = None
    doi: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    mesh_terms: List[str] = field(default_factory=list)
    publication_type: str = "journal-article"
    citations_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pmid": self.pmid,
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors,
            "journal": self.journal,
            "publication_date": self.publication_date.isoformat() if self.publication_date else None,
            "doi": self.doi,
            "keywords": self.keywords,
            "mesh_terms": self.mesh_terms,
            "publication_type": self.publication_type,
            "citations_count": self.citations_count,
        }


class PubMedClient(BaseAPIClient):
    """
    Client for PubMed E-utilities API.

    Free API for searching biomedical literature.
    Rate limit: 3 requests/second without API key, 10 req/sec with key
    """

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def __init__(self, api_key: Optional[str] = None, cache_ttl: int = 3600):
        config = APIClientConfig(
            base_url=self.BASE_URL,
            requests_per_second=10.0 if api_key else 3.0,  # 3 req/sec or 10 with key
            cache_ttl=cache_ttl,
        )
        super().__init__(config)
        self._api_key = api_key

    async def health_check(self) -> bool:
        """
        Check if the PubMed API is healthy and accessible.

        Returns:
            True if API is healthy, False otherwise
        """
        try:
            result = await self.search("test", max_results=1)
            return result.success
        except Exception as e:
            logger.warning(f"PubMed API health check failed: {e}")
            return False

    def _get_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Add API key to parameters if available."""
        if self._api_key:
            params["api_key"] = self._api_key
        return params

    async def search(
        self,
        query: str,
        max_results: int = 20,
        sort: str = "relevance",
        min_date: Optional[str] = None,
        max_date: Optional[str] = None,
    ) -> APIResponse:
        """
        Search PubMed for publications.

        Args:
            query: Search query (supports PubMed syntax)
            max_results: Maximum results to return
            sort: Sort order (relevance, pub_date)
            min_date: Minimum publication date (YYYY/MM/DD)
            max_date: Maximum publication date (YYYY/MM/DD)

        Returns:
            APIResponse with publication list
        """
        # First, get PMIDs via esearch
        search_url = f"{self.BASE_URL}/esearch.fcgi"
        params = self._get_params({
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "sort": sort,
            "retmode": "json",
        })

        if min_date:
            params["mindate"] = min_date
        if max_date:
            params["maxdate"] = max_date

        try:
            async with aiohttp.ClientSession() as session:
                # Search for PMIDs
                async with session.get(search_url, params=params) as response:
                    if response.status != 200:
                        return APIResponse(
                            success=False,
                            error=f"Search failed: {response.status}",
                            source="pubmed",
                        )

                    search_data = await response.json()
                    pmids = search_data.get("esearchresult", {}).get("idlist", [])
                    total_count = int(search_data.get("esearchresult", {}).get("count", 0))

                    if not pmids:
                        return APIResponse(
                            success=True,
                            data={"publications": [], "total_count": 0},
                            source="pubmed",
                        )

                # Fetch details for PMIDs
                publications = await self._fetch_details(session, pmids)

                return APIResponse(
                    success=True,
                    data={
                        "publications": [p.to_dict() for p in publications],
                        "total_count": total_count,
                        "returned_count": len(publications),
                    },
                    source="pubmed",
                )

        except Exception as e:
            logger.error(f"PubMed search failed: {e}")
            return APIResponse(success=False, error=str(e), source="pubmed")

    async def get_publication(self, pmid: str) -> APIResponse:
        """
        Get details for a specific publication.

        Args:
            pmid: PubMed ID

        Returns:
            APIResponse with publication details
        """
        try:
            async with aiohttp.ClientSession() as session:
                publications = await self._fetch_details(session, [pmid])
                if publications:
                    return APIResponse(
                        success=True,
                        data=publications[0].to_dict(),
                        source="pubmed",
                    )
                return APIResponse(
                    success=False,
                    error="Publication not found",
                    source="pubmed",
                )
        except Exception as e:
            logger.error(f"PubMed fetch failed: {e}")
            return APIResponse(success=False, error=str(e), source="pubmed")

    async def search_by_drug(
        self,
        drug_name: str,
        article_types: Optional[List[str]] = None,
        max_results: int = 50,
    ) -> APIResponse:
        """
        Search for publications about a drug.

        Args:
            drug_name: Name of the drug
            article_types: Filter by article type (review, clinical trial, etc.)
            max_results: Maximum results

        Returns:
            APIResponse with publications
        """
        # Build query
        query_parts = [f'"{drug_name}"[Title/Abstract]']

        if article_types:
            type_query = " OR ".join(f'"{t}"[Publication Type]' for t in article_types)
            query_parts.append(f"({type_query})")

        query = " AND ".join(query_parts)

        return await self.search(query=query, max_results=max_results, sort="pub_date")

    async def search_clinical_trials(
        self,
        drug_name: str,
        max_results: int = 50,
    ) -> APIResponse:
        """
        Search for clinical trial publications.

        Args:
            drug_name: Name of the drug
            max_results: Maximum results

        Returns:
            APIResponse with clinical trial publications
        """
        query = f'"{drug_name}"[Title/Abstract] AND ("Clinical Trial"[Publication Type] OR "Randomized Controlled Trial"[Publication Type])'
        return await self.search(query=query, max_results=max_results, sort="pub_date")

    async def _fetch_details(
        self,
        session: aiohttp.ClientSession,
        pmids: List[str],
    ) -> List[Publication]:
        """Fetch publication details for a list of PMIDs."""
        if not pmids:
            return []

        fetch_url = f"{self.BASE_URL}/efetch.fcgi"
        params = self._get_params({
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
        })

        async with session.get(fetch_url, params=params) as response:
            if response.status != 200:
                logger.error(f"Failed to fetch publication details: {response.status}")
                return []

            xml_text = await response.text()
            return self._parse_pubmed_xml(xml_text)

    def _parse_pubmed_xml(self, xml_text: str) -> List[Publication]:
        """Parse PubMed XML response."""
        publications = []

        try:
            root = ET.fromstring(xml_text)

            for article in root.findall(".//PubmedArticle"):
                try:
                    medline = article.find("MedlineCitation")
                    if medline is None:
                        continue

                    pmid_elem = medline.find("PMID")
                    pmid = pmid_elem.text if pmid_elem is not None else ""

                    article_elem = medline.find("Article")
                    if article_elem is None:
                        continue

                    # Title
                    title_elem = article_elem.find("ArticleTitle")
                    title = title_elem.text if title_elem is not None else ""

                    # Abstract
                    abstract_elem = article_elem.find(".//AbstractText")
                    abstract = abstract_elem.text if abstract_elem is not None else None

                    # Authors
                    authors = []
                    for author in article_elem.findall(".//Author"):
                        last_name = author.find("LastName")
                        fore_name = author.find("ForeName")
                        if last_name is not None:
                            name = last_name.text or ""
                            if fore_name is not None:
                                name = f"{fore_name.text} {name}"
                            authors.append(name)

                    # Journal
                    journal_elem = article_elem.find(".//Title")
                    journal = journal_elem.text if journal_elem is not None else None

                    # Publication date
                    pub_date = None
                    date_elem = article_elem.find(".//PubDate")
                    if date_elem is not None:
                        year = date_elem.find("Year")
                        month = date_elem.find("Month")
                        day = date_elem.find("Day")
                        if year is not None:
                            try:
                                year_val = int(year.text)
                                month_val = self._parse_month(month.text if month is not None else "1")
                                day_val = int(day.text) if day is not None else 1
                                pub_date = datetime(year_val, month_val, day_val)
                            except (ValueError, TypeError):
                                pass

                    # DOI
                    doi = None
                    for id_elem in article_elem.findall(".//ArticleId"):
                        if id_elem.get("IdType") == "doi":
                            doi = id_elem.text
                            break

                    # MeSH terms
                    mesh_terms = []
                    for mesh in medline.findall(".//MeshHeading/DescriptorName"):
                        if mesh.text:
                            mesh_terms.append(mesh.text)

                    # Keywords
                    keywords = []
                    for kw in medline.findall(".//Keyword"):
                        if kw.text:
                            keywords.append(kw.text)

                    publication = Publication(
                        pmid=pmid,
                        title=title,
                        abstract=abstract,
                        authors=authors,
                        journal=journal,
                        publication_date=pub_date,
                        doi=doi,
                        mesh_terms=mesh_terms,
                        keywords=keywords,
                    )
                    publications.append(publication)

                except Exception as e:
                    logger.warning(f"Failed to parse article: {e}")
                    continue

        except ET.ParseError as e:
            logger.error(f"Failed to parse PubMed XML: {e}")

        return publications

    def _parse_month(self, month_str: str) -> int:
        """Parse month string to integer."""
        month_map = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4,
            "may": 5, "jun": 6, "jul": 7, "aug": 8,
            "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        try:
            return int(month_str)
        except ValueError:
            return month_map.get(month_str.lower()[:3], 1)
