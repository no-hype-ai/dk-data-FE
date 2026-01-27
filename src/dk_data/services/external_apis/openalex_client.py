"""
OpenAlex API Client for scientific publication data.

Implements T139: OpenAlexClient class.

OpenAlex is a free, open catalog of the global research system.
API Documentation: https://docs.openalex.org/
Rate limit: 100,000 requests/day, 10 requests/second for polite pool
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List, Dict, Any
import aiohttp
from loguru import logger

from .base_client import BaseAPIClient, APIClientConfig


@dataclass
class Publication:
    """Scientific publication/work."""
    openalex_id: str
    doi: Optional[str] = None
    title: str = ""
    publication_date: Optional[date] = None
    publication_year: Optional[int] = None
    type: str = "article"  # article, review, book-chapter, etc.
    abstract: Optional[str] = None
    cited_by_count: int = 0
    authors: List[Dict[str, str]] = field(default_factory=list)
    institutions: List[str] = field(default_factory=list)
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    is_open_access: bool = False
    concepts: List[Dict[str, Any]] = field(default_factory=list)
    mesh_terms: List[str] = field(default_factory=list)
    url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "openalex_id": self.openalex_id,
            "doi": self.doi,
            "title": self.title,
            "publication_date": self.publication_date.isoformat() if self.publication_date else None,
            "publication_year": self.publication_year,
            "type": self.type,
            "abstract": self.abstract[:500] if self.abstract else None,
            "cited_by_count": self.cited_by_count,
            "authors": self.authors[:10],  # Limit authors
            "institutions": self.institutions[:5],
            "journal": self.journal,
            "is_open_access": self.is_open_access,
            "concepts": self.concepts[:5],
            "url": self.url,
        }


@dataclass
class Author:
    """Author/researcher information."""
    openalex_id: str
    display_name: str
    orcid: Optional[str] = None
    works_count: int = 0
    cited_by_count: int = 0
    h_index: Optional[int] = None
    affiliations: List[Dict[str, str]] = field(default_factory=list)
    concepts: List[Dict[str, Any]] = field(default_factory=list)


class OpenAlexClient(BaseAPIClient):
    """
    Client for OpenAlex API.

    OpenAlex provides free access to:
    - Publications (works)
    - Authors
    - Institutions
    - Concepts (topics)
    - Venues (journals)
    """

    BASE_URL = "https://api.openalex.org"

    def __init__(self, email: Optional[str] = None, cache_ttl: int = 3600):
        """
        Initialize OpenAlex client.

        Args:
            email: Contact email for polite pool (faster rate limits)
            cache_ttl: Cache TTL in seconds
        """
        config = APIClientConfig(
            base_url=self.BASE_URL,
            requests_per_second=10.0,  # 10 requests/second for polite pool
            cache_ttl=cache_ttl,
        )
        super().__init__(config)
        self._email = email or "api@example.com"

    async def health_check(self) -> bool:
        """Check if OpenAlex API is accessible."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/works?per_page=1",
                    params={"mailto": self._email},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    async def search_publications(
        self,
        query: str,
        filters: Optional[Dict[str, str]] = None,
        limit: int = 25,
        sort: str = "relevance_score:desc",
    ) -> List[Publication]:
        """
        Search for publications.

        Args:
            query: Search query (title, abstract, concepts)
            filters: Additional filters (e.g., publication_year, type)
            limit: Maximum number of results
            sort: Sort order (relevance_score, cited_by_count, publication_date)

        Returns:
            List of matching publications
        """
        logger.debug(f"Searching OpenAlex for: {query}")

        try:
            params = {
                "search": query,
                "per_page": min(limit, 200),  # API max is 200
                "sort": sort,
                "mailto": self._email,
            }

            # Add filters
            if filters:
                filter_parts = []
                for key, value in filters.items():
                    filter_parts.append(f"{key}:{value}")
                params["filter"] = ",".join(filter_parts)

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/works",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        logger.warning(f"OpenAlex API returned {response.status}")
                        return []

                    data = await response.json()
                    results = data.get("results", [])

                    return [self._parse_publication(item) for item in results]

        except Exception as e:
            logger.error(f"Error searching OpenAlex: {e}")
            return []

    async def get_publication(self, openalex_id: str) -> Optional[Publication]:
        """Get a specific publication by OpenAlex ID."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/works/{openalex_id}",
                    params={"mailto": self._email},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._parse_publication(data)
                    return None

        except Exception as e:
            logger.error(f"Error getting publication {openalex_id}: {e}")
            return None

    async def get_publications_by_drug(
        self,
        drug_name: str,
        years: int = 5,
        limit: int = 50,
    ) -> List[Publication]:
        """
        Get publications related to a drug.

        Args:
            drug_name: Name of the drug/molecule
            years: Number of years to look back
            limit: Maximum publications to return

        Returns:
            List of relevant publications
        """
        current_year = datetime.now().year
        filters = {
            "publication_year": f"{current_year - years}-{current_year}",
            "type": "article|review",
        }

        return await self.search_publications(
            query=drug_name,
            filters=filters,
            limit=limit,
            sort="cited_by_count:desc",
        )

    async def search_authors(
        self,
        query: str,
        limit: int = 25,
    ) -> List[Author]:
        """
        Search for authors/researchers.

        Args:
            query: Author name or ORCID
            limit: Maximum results

        Returns:
            List of matching authors
        """
        try:
            params = {
                "search": query,
                "per_page": min(limit, 200),
                "mailto": self._email,
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/authors",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        return []

                    data = await response.json()
                    results = data.get("results", [])

                    return [self._parse_author(item) for item in results]

        except Exception as e:
            logger.error(f"Error searching OpenAlex authors: {e}")
            return []

    async def get_trending_in_field(
        self,
        concept: str,
        days: int = 30,
        limit: int = 25,
    ) -> List[Publication]:
        """
        Get trending publications in a field.

        Args:
            concept: Field/concept (e.g., "Oncology", "Immunology")
            days: Recent days to consider
            limit: Maximum results

        Returns:
            List of trending publications
        """
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        filters = {
            "from_publication_date": cutoff,
            "concepts.display_name.search": concept,
        }

        return await self.search_publications(
            query="",
            filters=filters,
            limit=limit,
            sort="cited_by_count:desc",
        )

    def _parse_publication(self, data: Dict[str, Any]) -> Publication:
        """Parse API response into Publication."""
        # Parse authors
        authors = []
        for authorship in data.get("authorships", [])[:20]:
            author = authorship.get("author", {})
            authors.append({
                "name": author.get("display_name", ""),
                "orcid": author.get("orcid"),
                "position": authorship.get("author_position", ""),
            })

        # Parse institutions
        institutions = []
        for authorship in data.get("authorships", []):
            for inst in authorship.get("institutions", []):
                if inst.get("display_name") and inst["display_name"] not in institutions:
                    institutions.append(inst["display_name"])

        # Parse publication date
        pub_date = None
        pub_date_str = data.get("publication_date")
        if pub_date_str:
            try:
                pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        # Parse concepts
        concepts = [
            {"name": c.get("display_name"), "score": c.get("score")}
            for c in data.get("concepts", [])[:10]
        ]

        # Parse MeSH terms
        mesh_terms = [
            m.get("descriptor_name", "")
            for m in data.get("mesh", [])
        ]

        # Get journal/venue
        journal = None
        primary_location = data.get("primary_location") or {}
        source = primary_location.get("source") or {}
        journal = source.get("display_name")

        return Publication(
            openalex_id=data.get("id", ""),
            doi=data.get("doi"),
            title=data.get("title", ""),
            publication_date=pub_date,
            publication_year=data.get("publication_year"),
            type=data.get("type", "article"),
            abstract=data.get("abstract"),
            cited_by_count=data.get("cited_by_count", 0),
            authors=authors,
            institutions=institutions[:10],
            journal=journal,
            is_open_access=data.get("open_access", {}).get("is_oa", False),
            concepts=concepts,
            mesh_terms=mesh_terms,
            url=data.get("primary_location", {}).get("landing_page_url"),
        )

    def _parse_author(self, data: Dict[str, Any]) -> Author:
        """Parse API response into Author."""
        affiliations = []
        for aff in data.get("affiliations", []):
            inst = aff.get("institution", {})
            affiliations.append({
                "name": inst.get("display_name", ""),
                "country": inst.get("country_code"),
            })

        concepts = [
            {"name": c.get("display_name"), "score": c.get("score")}
            for c in data.get("x_concepts", [])[:10]
        ]

        return Author(
            openalex_id=data.get("id", ""),
            display_name=data.get("display_name", ""),
            orcid=data.get("orcid"),
            works_count=data.get("works_count", 0),
            cited_by_count=data.get("cited_by_count", 0),
            h_index=data.get("summary_stats", {}).get("h_index"),
            affiliations=affiliations,
            concepts=concepts,
        )
