"""
Europe PMC API Client.

Europe PMC provides free access to a worldwide collection of life science
publications and preprints, with strong coverage of European research.

API Documentation: https://europepmc.org/RestfulWebService
Rate limit: 10 requests/second
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
import aiohttp
from loguru import logger

from .base_client import BaseAPIClient, APIClientConfig


@dataclass
class EuropePMCPublication:
    """Publication from Europe PMC."""
    pmcid: Optional[str] = None
    pmid: Optional[str] = None
    doi: Optional[str] = None
    title: str = ""
    abstract: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    journal: Optional[str] = None
    publication_date: Optional[date] = None
    publication_year: Optional[int] = None
    cited_by_count: int = 0
    is_open_access: bool = False
    source: str = "europepmc"
    full_text_available: bool = False
    publication_type: str = "research-article"
    mesh_terms: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pmcid": self.pmcid,
            "pmid": self.pmid,
            "doi": self.doi,
            "title": self.title,
            "abstract": self.abstract[:500] if self.abstract else None,
            "authors": self.authors[:10],
            "journal": self.journal,
            "publication_date": self.publication_date.isoformat() if self.publication_date else None,
            "publication_year": self.publication_year,
            "cited_by_count": self.cited_by_count,
            "is_open_access": self.is_open_access,
            "source": self.source,
            "full_text_available": self.full_text_available,
            "publication_type": self.publication_type,
        }


class EuropePMCClient(BaseAPIClient):
    """
    Client for Europe PMC REST API.

    Europe PMC aggregates content from:
    - PubMed/MEDLINE
    - PubMed Central (full-text)
    - European Patent Office
    - Preprints (bioRxiv, medRxiv)
    - Clinical trials (WHO ICTRP)
    - Agricultural research
    """

    BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"

    def __init__(self, cache_ttl: int = 3600):
        """Initialize Europe PMC client."""
        config = APIClientConfig(
            base_url=self.BASE_URL,
            requests_per_second=10.0,
            cache_ttl=cache_ttl,
        )
        super().__init__(config)

    async def health_check(self) -> bool:
        """Check if Europe PMC API is accessible."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/search",
                    params={"query": "test", "format": "json", "pageSize": 1},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    async def search(
        self,
        query: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        source: Optional[str] = None,
        publication_type: Optional[str] = None,
        open_access_only: bool = False,
        limit: int = 100,
        sort: str = "RELEVANCE",
    ) -> List[EuropePMCPublication]:
        """
        Search Europe PMC for publications.

        Args:
            query: Search query (supports Lucene syntax)
            from_date: Start date for publication date filter
            to_date: End date for publication date filter
            source: Source filter (MED, PMC, PPR for preprints, etc.)
            publication_type: Filter by publication type
            open_access_only: Only return open access publications
            limit: Maximum results to return
            sort: Sort order (RELEVANCE, P_PDATE_D for date desc)

        Returns:
            List of publications
        """
        logger.debug(f"Searching Europe PMC for: {query}")

        # Build query with filters
        query_parts = [query]

        if from_date:
            query_parts.append(f"FIRST_PDATE:[{from_date.strftime('%Y-%m-%d')} TO *]")
        if to_date:
            query_parts.append(f"FIRST_PDATE:[* TO {to_date.strftime('%Y-%m-%d')}]")
        if source:
            query_parts.append(f"SRC:{source}")
        if open_access_only:
            query_parts.append("OPEN_ACCESS:y")
        if publication_type:
            query_parts.append(f"PUB_TYPE:\"{publication_type}\"")

        full_query = " AND ".join(query_parts)

        try:
            publications = []
            cursor_mark = "*"
            fetched = 0

            async with aiohttp.ClientSession() as session:
                while fetched < limit:
                    page_size = min(100, limit - fetched)
                    params = {
                        "query": full_query,
                        "format": "json",
                        "pageSize": page_size,
                        "sort": sort,
                        "cursorMark": cursor_mark,
                    }

                    async with session.get(
                        f"{self.BASE_URL}/search",
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        if response.status != 200:
                            logger.warning(f"Europe PMC API returned {response.status}")
                            break

                        data = await response.json()
                        results = data.get("resultList", {}).get("result", [])

                        if not results:
                            break

                        for item in results:
                            pub = self._parse_publication(item)
                            publications.append(pub)
                            fetched += 1

                            if fetched >= limit:
                                break

                        # Check for more pages
                        next_cursor = data.get("nextCursorMark")
                        if not next_cursor or next_cursor == cursor_mark:
                            break
                        cursor_mark = next_cursor

            logger.info(f"Europe PMC: Found {len(publications)} publications")
            return publications

        except Exception as e:
            logger.error(f"Error searching Europe PMC: {e}")
            return []

    async def get_by_pmcid(self, pmcid: str) -> Optional[EuropePMCPublication]:
        """Get publication by PMC ID."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/search",
                    params={"query": f"PMCID:{pmcid}", "format": "json"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("resultList", {}).get("result", [])
                        if results:
                            return self._parse_publication(results[0])
            return None
        except Exception as e:
            logger.error(f"Error getting PMC article {pmcid}: {e}")
            return None

    async def get_by_pmid(self, pmid: str) -> Optional[EuropePMCPublication]:
        """Get publication by PubMed ID."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/search",
                    params={"query": f"EXT_ID:{pmid} AND SRC:MED", "format": "json"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("resultList", {}).get("result", [])
                        if results:
                            return self._parse_publication(results[0])
            return None
        except Exception as e:
            logger.error(f"Error getting PubMed article {pmid}: {e}")
            return None

    async def get_citations(self, pmcid: str, limit: int = 50) -> List[EuropePMCPublication]:
        """Get articles that cite a given PMC article."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/{pmcid}/citations",
                    params={"format": "json", "page": 1, "pageSize": limit},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        citations = data.get("citationList", {}).get("citation", [])
                        return [self._parse_citation(c) for c in citations]
            return []
        except Exception as e:
            logger.error(f"Error getting citations for {pmcid}: {e}")
            return []

    async def search_preprints(
        self,
        query: str,
        days_back: int = 90,
        limit: int = 50,
    ) -> List[EuropePMCPublication]:
        """
        Search specifically for preprints (bioRxiv, medRxiv).

        Args:
            query: Search query
            days_back: Days to look back
            limit: Maximum results

        Returns:
            List of preprint publications
        """
        from_date = date.today() - timedelta(days=days_back)
        return await self.search(
            query=query,
            from_date=from_date,
            source="PPR",  # Preprint source
            limit=limit,
            sort="P_PDATE_D",  # Sort by date descending
        )

    async def search_clinical_evidence(
        self,
        drug_name: str,
        indication: Optional[str] = None,
        years_back: int = 5,
        limit: int = 100,
    ) -> List[EuropePMCPublication]:
        """
        Search for clinical evidence publications.

        Args:
            drug_name: Drug name to search
            indication: Optional indication filter
            years_back: Years to look back
            limit: Maximum results

        Returns:
            List of clinical publications
        """
        # Build clinical evidence query
        query_parts = [f'"{drug_name}"']

        if indication:
            query_parts.append(f'"{indication}"')

        # Add clinical evidence terms
        clinical_terms = [
            "clinical trial",
            "randomized controlled trial",
            "real-world",
            "registry",
            "cohort study",
        ]
        clinical_query = " OR ".join([f'"{t}"' for t in clinical_terms])
        query_parts.append(f"({clinical_query})")

        from_date = date.today() - timedelta(days=years_back * 365)

        return await self.search(
            query=" AND ".join(query_parts),
            from_date=from_date,
            limit=limit,
            sort="RELEVANCE",
        )

    def _parse_publication(self, data: Dict[str, Any]) -> EuropePMCPublication:
        """Parse API response into EuropePMCPublication."""
        # Parse authors
        authors = []
        author_list = data.get("authorList", {}).get("author", [])
        if isinstance(author_list, list):
            for author in author_list[:20]:
                if isinstance(author, dict):
                    name = author.get("fullName", "")
                    if name:
                        authors.append(name)

        # Parse publication date
        pub_date = None
        pub_year = None
        date_str = data.get("firstPublicationDate")
        if date_str:
            try:
                pub_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                pub_year = pub_date.year
            except (ValueError, TypeError):
                year_str = data.get("pubYear")
                if year_str:
                    try:
                        pub_year = int(year_str)
                    except (ValueError, TypeError):
                        pass

        # Parse MeSH terms
        mesh_terms = []
        mesh_list = data.get("meshHeadingList", {}).get("meshHeading", [])
        if isinstance(mesh_list, list):
            for mesh in mesh_list:
                if isinstance(mesh, dict):
                    term = mesh.get("descriptorName")
                    if term:
                        mesh_terms.append(term)

        # Parse keywords
        keywords = []
        kw_list = data.get("keywordList", {}).get("keyword", [])
        if isinstance(kw_list, list):
            keywords = [kw for kw in kw_list if isinstance(kw, str)]

        return EuropePMCPublication(
            pmcid=data.get("pmcid"),
            pmid=data.get("pmid"),
            doi=data.get("doi"),
            title=data.get("title", ""),
            abstract=data.get("abstractText"),
            authors=authors,
            journal=data.get("journalTitle"),
            publication_date=pub_date,
            publication_year=pub_year,
            cited_by_count=data.get("citedByCount", 0),
            is_open_access=data.get("isOpenAccess") == "Y",
            full_text_available=data.get("inEPMC") == "Y",
            publication_type=data.get("pubType", "research-article"),
            mesh_terms=mesh_terms,
            keywords=keywords,
        )

    def _parse_citation(self, data: Dict[str, Any]) -> EuropePMCPublication:
        """Parse citation data into EuropePMCPublication."""
        return EuropePMCPublication(
            pmcid=data.get("pmcid"),
            pmid=data.get("pmid"),
            doi=data.get("doi"),
            title=data.get("title", ""),
            authors=[data.get("authorString", "")] if data.get("authorString") else [],
            journal=data.get("journalAbbreviation"),
            publication_year=data.get("pubYear"),
        )
