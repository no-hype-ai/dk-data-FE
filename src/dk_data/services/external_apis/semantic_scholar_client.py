"""
Semantic Scholar API Client.

Semantic Scholar provides access to a large corpus of academic papers
with advanced features like citation analysis, influential citations,
and AI-powered recommendations.

API Documentation: https://api.semanticscholar.org/
Rate limit: 100 requests/5 minutes (unauthenticated), 1 request/second with API key
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List, Dict, Any
import aiohttp
import asyncio
from loguru import logger

from .base_client import BaseAPIClient, APIClientConfig


@dataclass
class SemanticScholarPaper:
    """Paper from Semantic Scholar."""
    paper_id: str
    title: str = ""
    abstract: Optional[str] = None
    authors: List[Dict[str, str]] = field(default_factory=list)
    venue: Optional[str] = None
    publication_date: Optional[date] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    arxiv_id: Optional[str] = None
    citation_count: int = 0
    influential_citation_count: int = 0
    reference_count: int = 0
    is_open_access: bool = False
    open_access_url: Optional[str] = None
    fields_of_study: List[str] = field(default_factory=list)
    tldr: Optional[str] = None  # AI-generated summary
    source: str = "semantic_scholar"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "abstract": self.abstract[:500] if self.abstract else None,
            "authors": [a.get("name", "") for a in self.authors[:10]],
            "venue": self.venue,
            "publication_date": self.publication_date.isoformat() if self.publication_date else None,
            "year": self.year,
            "doi": self.doi,
            "pmid": self.pmid,
            "citation_count": self.citation_count,
            "influential_citation_count": self.influential_citation_count,
            "is_open_access": self.is_open_access,
            "fields_of_study": self.fields_of_study,
            "tldr": self.tldr,
            "source": self.source,
        }


class SemanticScholarClient(BaseAPIClient):
    """
    Client for Semantic Scholar API.

    Features:
    - Large academic paper corpus
    - Citation and reference graphs
    - Influential citation detection
    - AI-generated paper summaries (TLDR)
    - Author profiles and metrics
    """

    BASE_URL = "https://api.semanticscholar.org/graph/v1"

    # Fields to request from the API
    PAPER_FIELDS = [
        "paperId", "title", "abstract", "venue", "year",
        "publicationDate", "citationCount", "influentialCitationCount",
        "referenceCount", "isOpenAccess", "openAccessPdf",
        "fieldsOfStudy", "tldr", "authors", "externalIds",
    ]

    def __init__(self, api_key: Optional[str] = None, cache_ttl: int = 3600):
        """
        Initialize Semantic Scholar client.

        Args:
            api_key: Optional API key for higher rate limits
            cache_ttl: Cache TTL in seconds
        """
        config = APIClientConfig(
            base_url=self.BASE_URL,
            requests_per_second=1.0 if api_key else 0.33,  # 100 req/5 min without key
            cache_ttl=cache_ttl,
        )
        super().__init__(config)
        self._api_key = api_key
        self._headers = {"x-api-key": api_key} if api_key else {}

    async def health_check(self) -> bool:
        """Check if Semantic Scholar API is accessible."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/paper/search",
                    params={"query": "test", "limit": 1},
                    headers=self._headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    async def search(
        self,
        query: str,
        year_range: Optional[tuple] = None,
        fields_of_study: Optional[List[str]] = None,
        open_access_only: bool = False,
        min_citation_count: int = 0,
        limit: int = 100,
    ) -> List[SemanticScholarPaper]:
        """
        Search for papers.

        Args:
            query: Search query
            year_range: Tuple of (start_year, end_year)
            fields_of_study: Filter by fields (e.g., ["Medicine", "Biology"])
            open_access_only: Only return open access papers
            min_citation_count: Minimum citation count filter
            limit: Maximum results to return

        Returns:
            List of papers
        """
        logger.debug(f"Searching Semantic Scholar for: {query}")

        try:
            papers = []
            offset = 0
            batch_size = min(100, limit)

            async with aiohttp.ClientSession() as session:
                while len(papers) < limit:
                    params = {
                        "query": query,
                        "fields": ",".join(self.PAPER_FIELDS),
                        "offset": offset,
                        "limit": batch_size,
                    }

                    if year_range:
                        params["year"] = f"{year_range[0]}-{year_range[1]}"
                    if fields_of_study:
                        params["fieldsOfStudy"] = ",".join(fields_of_study)
                    if open_access_only:
                        params["openAccessPdf"] = ""
                    if min_citation_count > 0:
                        params["minCitationCount"] = min_citation_count

                    async with session.get(
                        f"{self.BASE_URL}/paper/search",
                        params=params,
                        headers=self._headers,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        if response.status == 429:
                            logger.warning("Semantic Scholar rate limited, waiting...")
                            await asyncio.sleep(5)
                            continue

                        if response.status != 200:
                            logger.warning(f"Semantic Scholar API returned {response.status}")
                            break

                        data = await response.json()
                        results = data.get("data", [])

                        if not results:
                            break

                        for item in results:
                            paper = self._parse_paper(item)
                            papers.append(paper)

                            if len(papers) >= limit:
                                break

                        # Check if more results available
                        total = data.get("total", 0)
                        offset += batch_size
                        if offset >= total:
                            break

                    # Small delay to avoid rate limiting
                    await asyncio.sleep(0.5)

            logger.info(f"Semantic Scholar: Found {len(papers)} papers")
            return papers

        except Exception as e:
            logger.error(f"Error searching Semantic Scholar: {e}")
            return []

    async def get_paper(self, paper_id: str) -> Optional[SemanticScholarPaper]:
        """
        Get a specific paper by ID.

        Args:
            paper_id: Semantic Scholar paper ID, DOI, ArXiv ID, or PMID

        Returns:
            Paper details or None
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/paper/{paper_id}",
                    params={"fields": ",".join(self.PAPER_FIELDS)},
                    headers=self._headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._parse_paper(data)
            return None
        except Exception as e:
            logger.error(f"Error getting paper {paper_id}: {e}")
            return None

    async def get_paper_by_doi(self, doi: str) -> Optional[SemanticScholarPaper]:
        """Get paper by DOI."""
        return await self.get_paper(f"DOI:{doi}")

    async def get_paper_by_pmid(self, pmid: str) -> Optional[SemanticScholarPaper]:
        """Get paper by PubMed ID."""
        return await self.get_paper(f"PMID:{pmid}")

    async def get_citations(
        self,
        paper_id: str,
        limit: int = 100,
        influential_only: bool = False,
    ) -> List[SemanticScholarPaper]:
        """
        Get papers that cite a given paper.

        Args:
            paper_id: Paper ID
            limit: Maximum citations to return
            influential_only: Only return influential citations

        Returns:
            List of citing papers
        """
        try:
            papers = []
            offset = 0
            batch_size = min(100, limit)

            async with aiohttp.ClientSession() as session:
                while len(papers) < limit:
                    params = {
                        "fields": ",".join(self.PAPER_FIELDS),
                        "offset": offset,
                        "limit": batch_size,
                    }

                    async with session.get(
                        f"{self.BASE_URL}/paper/{paper_id}/citations",
                        params=params,
                        headers=self._headers,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        if response.status != 200:
                            break

                        data = await response.json()
                        citations = data.get("data", [])

                        if not citations:
                            break

                        for item in citations:
                            citing_paper = item.get("citingPaper", {})
                            is_influential = item.get("isInfluential", False)

                            if influential_only and not is_influential:
                                continue

                            paper = self._parse_paper(citing_paper)
                            papers.append(paper)

                            if len(papers) >= limit:
                                break

                        offset += batch_size

                    await asyncio.sleep(0.5)

            return papers

        except Exception as e:
            logger.error(f"Error getting citations for {paper_id}: {e}")
            return []

    async def get_references(
        self,
        paper_id: str,
        limit: int = 100,
    ) -> List[SemanticScholarPaper]:
        """
        Get papers referenced by a given paper.

        Args:
            paper_id: Paper ID
            limit: Maximum references to return

        Returns:
            List of referenced papers
        """
        try:
            papers = []
            offset = 0
            batch_size = min(100, limit)

            async with aiohttp.ClientSession() as session:
                while len(papers) < limit:
                    params = {
                        "fields": ",".join(self.PAPER_FIELDS),
                        "offset": offset,
                        "limit": batch_size,
                    }

                    async with session.get(
                        f"{self.BASE_URL}/paper/{paper_id}/references",
                        params=params,
                        headers=self._headers,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        if response.status != 200:
                            break

                        data = await response.json()
                        references = data.get("data", [])

                        if not references:
                            break

                        for item in references:
                            cited_paper = item.get("citedPaper", {})
                            paper = self._parse_paper(cited_paper)
                            papers.append(paper)

                            if len(papers) >= limit:
                                break

                        offset += batch_size

                    await asyncio.sleep(0.5)

            return papers

        except Exception as e:
            logger.error(f"Error getting references for {paper_id}: {e}")
            return []

    async def get_recommendations(
        self,
        paper_ids: List[str],
        limit: int = 50,
    ) -> List[SemanticScholarPaper]:
        """
        Get paper recommendations based on a list of papers.

        Args:
            paper_ids: List of paper IDs to base recommendations on
            limit: Maximum recommendations to return

        Returns:
            List of recommended papers
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.BASE_URL}/paper/batch",
                    json={"ids": paper_ids},
                    params={"fields": ",".join(self.PAPER_FIELDS)},
                    headers={**self._headers, "Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        return []

                    data = await response.json()
                    return [self._parse_paper(p) for p in data[:limit] if p]

        except Exception as e:
            logger.error(f"Error getting recommendations: {e}")
            return []

    async def search_clinical_papers(
        self,
        drug_name: str,
        indication: Optional[str] = None,
        years_back: int = 5,
        limit: int = 100,
    ) -> List[SemanticScholarPaper]:
        """
        Search for clinical/biomedical papers about a drug.

        Args:
            drug_name: Drug name to search
            indication: Optional indication filter
            years_back: Years to look back
            limit: Maximum results

        Returns:
            List of relevant papers
        """
        # Build search query
        query_parts = [drug_name]
        if indication:
            query_parts.append(indication)

        # Add clinical terms
        query_parts.append("(clinical OR trial OR efficacy OR safety OR real-world)")

        current_year = datetime.now().year
        year_range = (current_year - years_back, current_year)

        return await self.search(
            query=" ".join(query_parts),
            year_range=year_range,
            fields_of_study=["Medicine", "Biology"],
            limit=limit,
        )

    async def find_influential_papers(
        self,
        query: str,
        min_citations: int = 50,
        limit: int = 50,
    ) -> List[SemanticScholarPaper]:
        """
        Find highly influential papers on a topic.

        Args:
            query: Search query
            min_citations: Minimum citation count
            limit: Maximum results

        Returns:
            List of influential papers sorted by citations
        """
        papers = await self.search(
            query=query,
            min_citation_count=min_citations,
            limit=limit * 2,  # Fetch more to sort
        )

        # Sort by citation count
        papers.sort(key=lambda p: p.citation_count, reverse=True)
        return papers[:limit]

    def _parse_paper(self, data: Dict[str, Any]) -> SemanticScholarPaper:
        """Parse API response into SemanticScholarPaper."""
        if not data:
            return SemanticScholarPaper(paper_id="unknown")

        # Parse publication date
        pub_date = None
        year = data.get("year")
        date_str = data.get("publicationDate")
        if date_str:
            try:
                pub_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass

        # Parse external IDs
        external_ids = data.get("externalIds", {}) or {}
        doi = external_ids.get("DOI")
        pmid = external_ids.get("PubMed")
        arxiv_id = external_ids.get("ArXiv")

        # Parse open access PDF
        oa_pdf = data.get("openAccessPdf", {}) or {}
        is_oa = bool(oa_pdf)
        oa_url = oa_pdf.get("url") if isinstance(oa_pdf, dict) else None

        # Parse TLDR
        tldr_data = data.get("tldr", {}) or {}
        tldr = tldr_data.get("text") if isinstance(tldr_data, dict) else None

        # Parse fields of study
        fields = data.get("fieldsOfStudy", []) or []

        return SemanticScholarPaper(
            paper_id=data.get("paperId", "unknown"),
            title=data.get("title", ""),
            abstract=data.get("abstract"),
            authors=data.get("authors", []) or [],
            venue=data.get("venue"),
            publication_date=pub_date,
            year=year,
            doi=doi,
            pmid=pmid,
            arxiv_id=arxiv_id,
            citation_count=data.get("citationCount", 0) or 0,
            influential_citation_count=data.get("influentialCitationCount", 0) or 0,
            reference_count=data.get("referenceCount", 0) or 0,
            is_open_access=is_oa,
            open_access_url=oa_url,
            fields_of_study=fields,
            tldr=tldr,
        )
