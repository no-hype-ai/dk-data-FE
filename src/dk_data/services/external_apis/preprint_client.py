"""
bioRxiv/medRxiv Preprint Client.

Implements T140: PrePrintClient class for bioRxiv and medRxiv preprints.

API Documentation:
- bioRxiv: https://api.biorxiv.org/
- medRxiv: https://api.medrxiv.org/
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
import aiohttp
from loguru import logger

from .base_client import BaseAPIClient, APIClientConfig


@dataclass
class Preprint:
    """Preprint article."""
    doi: str
    title: str
    authors: str
    author_list: List[str] = field(default_factory=list)
    abstract: Optional[str] = None
    date_posted: Optional[date] = None
    server: str = "biorxiv"  # biorxiv or medrxiv
    category: Optional[str] = None
    version: int = 1
    published_doi: Optional[str] = None  # DOI if published in journal
    license: Optional[str] = None
    url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "doi": self.doi,
            "title": self.title,
            "authors": self.authors,
            "author_list": self.author_list[:10],
            "abstract": self.abstract[:500] if self.abstract else None,
            "date_posted": self.date_posted.isoformat() if self.date_posted else None,
            "server": self.server,
            "category": self.category,
            "version": self.version,
            "published_doi": self.published_doi,
            "url": self.url,
        }


class PrePrintClient(BaseAPIClient):
    """
    Client for bioRxiv and medRxiv preprint servers.

    These servers host preprints (not yet peer-reviewed) in:
    - bioRxiv: Biology and life sciences
    - medRxiv: Medical and health sciences
    """

    BIORXIV_API = "https://api.biorxiv.org"
    MEDRXIV_API = "https://api.medrxiv.org"

    def __init__(self, cache_ttl: int = 1800):  # 30 minute cache
        config = APIClientConfig(
            base_url=self.BIORXIV_API,
            requests_per_second=1.0,  # 1 request per second
            cache_ttl=cache_ttl,
        )
        super().__init__(config)

    async def search_biorxiv(
        self,
        query: str,
        days: int = 30,
        limit: int = 25,
    ) -> List[Preprint]:
        """
        Search bioRxiv preprints.

        Args:
            query: Search query
            days: Look back period in days
            limit: Maximum results

        Returns:
            List of matching preprints
        """
        return await self._search_server(
            server="biorxiv",
            query=query,
            days=days,
            limit=limit,
        )

    async def search_medrxiv(
        self,
        query: str,
        days: int = 30,
        limit: int = 25,
    ) -> List[Preprint]:
        """
        Search medRxiv preprints.

        Args:
            query: Search query
            days: Look back period in days
            limit: Maximum results

        Returns:
            List of matching preprints
        """
        return await self._search_server(
            server="medrxiv",
            query=query,
            days=days,
            limit=limit,
        )

    async def search_both(
        self,
        query: str,
        days: int = 30,
        limit: int = 25,
    ) -> List[Preprint]:
        """
        Search both bioRxiv and medRxiv.

        Args:
            query: Search query
            days: Look back period in days
            limit: Maximum results per server

        Returns:
            Combined list of preprints sorted by date
        """
        biorxiv = await self.search_biorxiv(query, days, limit)
        medrxiv = await self.search_medrxiv(query, days, limit)

        combined = biorxiv + medrxiv
        combined.sort(key=lambda x: x.date_posted or date.min, reverse=True)

        return combined[:limit * 2]

    async def _search_server(
        self,
        server: str,
        query: str,
        days: int,
        limit: int,
    ) -> List[Preprint]:
        """Search a specific preprint server."""
        base_url = self.MEDRXIV_API if server == "medrxiv" else self.BIORXIV_API

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # The API uses format: /details/[server]/[YYYY-MM-DD]/[YYYY-MM-DD]/[cursor]
        endpoint = f"/details/{server}/{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}/0"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{base_url}{endpoint}",
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        logger.warning(f"{server} API returned {response.status}")
                        return []

                    data = await response.json()
                    collection = data.get("collection", [])

                    # Filter by query
                    query_lower = query.lower()
                    filtered = [
                        item for item in collection
                        if query_lower in item.get("title", "").lower()
                        or query_lower in item.get("abstract", "").lower()
                        or query_lower in item.get("authors", "").lower()
                    ]

                    return [
                        self._parse_preprint(item, server)
                        for item in filtered[:limit]
                    ]

        except Exception as e:
            logger.error(f"Error searching {server}: {e}")
            return []

    async def get_recent_preprints(
        self,
        server: str = "medrxiv",
        days: int = 7,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> List[Preprint]:
        """
        Get recent preprints from a server.

        Args:
            server: "biorxiv" or "medrxiv"
            days: Number of days to look back
            category: Filter by category (e.g., "pharmacology", "oncology")
            limit: Maximum results

        Returns:
            List of recent preprints
        """
        base_url = self.MEDRXIV_API if server == "medrxiv" else self.BIORXIV_API

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        endpoint = f"/details/{server}/{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}/0"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{base_url}{endpoint}",
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        return []

                    data = await response.json()
                    collection = data.get("collection", [])

                    # Filter by category if specified
                    if category:
                        category_lower = category.lower()
                        collection = [
                            item for item in collection
                            if category_lower in (item.get("category", "") or "").lower()
                        ]

                    return [
                        self._parse_preprint(item, server)
                        for item in collection[:limit]
                    ]

        except Exception as e:
            logger.error(f"Error getting recent preprints: {e}")
            return []

    async def get_drug_preprints(
        self,
        drug_name: str,
        days: int = 90,
        limit: int = 25,
    ) -> List[Preprint]:
        """
        Get preprints related to a drug.

        Searches both bioRxiv and medRxiv.

        Args:
            drug_name: Name of the drug
            days: Days to look back
            limit: Maximum results

        Returns:
            List of relevant preprints
        """
        return await self.search_both(drug_name, days, limit)

    def _parse_preprint(self, data: Dict[str, Any], server: str) -> Preprint:
        """Parse API response into Preprint."""
        # Parse date
        date_posted = None
        date_str = data.get("date")
        if date_str:
            try:
                date_posted = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        # Parse authors into list
        authors_str = data.get("authors", "")
        author_list = [a.strip() for a in authors_str.split(";") if a.strip()]

        # Get DOI and build URL
        doi = data.get("doi", "")
        url = f"https://doi.org/{doi}" if doi else None

        return Preprint(
            doi=doi,
            title=data.get("title", ""),
            authors=authors_str,
            author_list=author_list,
            abstract=data.get("abstract"),
            date_posted=date_posted,
            server=server,
            category=data.get("category"),
            version=int(data.get("version", 1)),
            published_doi=data.get("published"),  # DOI of published version
            license=data.get("license"),
            url=url,
        )

    async def health_check(self) -> bool:
        """Check if preprint APIs are accessible."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BIORXIV_API}/details/biorxiv/2024-01-01/2024-01-02/0",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    return response.status < 500
        except Exception:
            return False
