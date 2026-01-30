"""
Web Search API Client.

Provides integration with search engines for drug-related:
- News articles
- Academic publications
- Press releases
- Regulatory announcements

Supports multiple search backends (configurable).
"""

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from loguru import logger

from .base_client import APIClientConfig, APIResponse, BaseAPIClient
from .cache_manager import CacheManager


@dataclass
class SearchResult:
    """A single search result."""

    title: str
    url: str
    snippet: str
    source: str
    published_date: Optional[datetime] = None
    authors: List[str] = field(default_factory=list)
    relevance_score: Optional[float] = None
    result_type: str = "general"  # general, news, academic

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source": self.source,
            "published_date": self.published_date.isoformat() if self.published_date else None,
            "authors": self.authors,
            "relevance_score": self.relevance_score,
            "result_type": self.result_type,
        }


@dataclass
class SearchResponse:
    """Response from a search query."""

    query: str
    total_results: int
    results: List[SearchResult]
    search_engine: str
    search_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "total_results": self.total_results,
            "results": [r.to_dict() for r in self.results],
            "search_engine": self.search_engine,
            "search_time_ms": self.search_time_ms,
        }


class WebSearchClient(BaseAPIClient[Dict[str, Any]]):
    """
    Client for web search APIs.

    Supports multiple search backends:
    - NewsAPI for news articles
    - SerpAPI for Google/Scholar results
    - Bing News API

    API keys should be set via environment variables:
    - NEWSAPI_KEY
    - SERPAPI_KEY
    - BING_NEWS_KEY

    Usage:
        client = WebSearchClient()
        results = await client.search_news("pembrolizumab FDA approval")
    """

    # Search engine configurations
    ENGINES = {
        "newsapi": {
            "base_url": "https://newsapi.org/v2",
            "env_key": "NEWSAPI_KEY",
        },
        "serpapi": {
            "base_url": "https://serpapi.com",
            "env_key": "SERPAPI_KEY",
        },
        "bing_news": {
            "base_url": "https://api.bing.microsoft.com/v7.0",
            "env_key": "BING_NEWS_KEY",
        },
    }

    def __init__(
        self,
        cache_manager: Optional[CacheManager] = None,
        preferred_engine: str = "newsapi",
    ):
        # Use NewsAPI as default
        engine_config = self.ENGINES.get(preferred_engine, self.ENGINES["newsapi"])

        config = APIClientConfig(
            base_url=engine_config["base_url"],
            timeout=30.0,
            max_retries=3,
            requests_per_second=1.0,  # Be conservative with search APIs
            cache_ttl=3600,  # 1 hour cache for search results
        )
        super().__init__(config, cache_manager)

        self.preferred_engine = preferred_engine
        self._api_key = os.environ.get(engine_config["env_key"], "")

    async def health_check(self) -> bool:
        """Check if search API is accessible."""
        if not self._api_key:
            logger.warning(f"No API key configured for {self.preferred_engine}")
            return False

        try:
            # Test with a simple query
            result = await self.search_news("test", limit=1)
            return result.success
        except Exception as e:
            logger.error(f"Web search health check failed: {e}")
            return False

    async def search_news(
        self,
        query: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        language: str = "en",
        limit: int = 20,
        sort_by: str = "publishedAt",
    ) -> APIResponse:
        """
        Search for news articles.

        Args:
            query: Search query (drug name, trial ID, etc.)
            from_date: Start date filter
            to_date: End date filter
            language: Language code (default: en)
            limit: Maximum results (default: 20)
            sort_by: Sort order (publishedAt, relevancy, popularity)

        Returns:
            APIResponse with SearchResponse data
        """
        try:
            if self.preferred_engine == "newsapi":
                return await self._search_newsapi(
                    query, from_date, to_date, language, limit, sort_by
                )
            elif self.preferred_engine == "bing_news":
                return await self._search_bing_news(
                    query, from_date, limit
                )
            else:
                return await self._search_serpapi_news(
                    query, from_date, limit
                )

        except Exception as e:
            logger.error(f"News search error for '{query}': {e}")
            return APIResponse(success=False, error=str(e))

    async def _search_newsapi(
        self,
        query: str,
        from_date: Optional[datetime],
        to_date: Optional[datetime],
        language: str,
        limit: int,
        sort_by: str,
    ) -> APIResponse:
        """Search using NewsAPI."""
        if not self._api_key:
            return APIResponse(
                success=False,
                error="NewsAPI key not configured. Set NEWSAPI_KEY environment variable.",
            )

        params = {
            "q": query,
            "language": language,
            "pageSize": min(limit, 100),
            "sortBy": sort_by,
            "apiKey": self._api_key,
        }

        if from_date:
            params["from"] = from_date.strftime("%Y-%m-%d")
        if to_date:
            params["to"] = to_date.strftime("%Y-%m-%d")

        result = await self._get("/everything", params=params)

        if result.get("status") != "ok":
            return APIResponse(
                success=False,
                error=result.get("message", "Unknown NewsAPI error"),
            )

        articles = result.get("articles", [])
        results = []

        for article in articles:
            pub_date = None
            if article.get("publishedAt"):
                try:
                    pub_date = datetime.fromisoformat(
                        article["publishedAt"].replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            results.append(
                SearchResult(
                    title=article.get("title", ""),
                    url=article.get("url", ""),
                    snippet=article.get("description", ""),
                    source=article.get("source", {}).get("name", "Unknown"),
                    published_date=pub_date,
                    authors=[article["author"]] if article.get("author") else [],
                    result_type="news",
                )
            )

        response = SearchResponse(
            query=query,
            total_results=result.get("totalResults", len(results)),
            results=results,
            search_engine="newsapi",
        )

        return APIResponse(success=True, data=response.to_dict(), source="websearch")

    async def _search_bing_news(
        self,
        query: str,
        from_date: Optional[datetime],
        limit: int,
    ) -> APIResponse:
        """Search using Bing News API."""
        if not self._api_key:
            return APIResponse(
                success=False,
                error="Bing News key not configured. Set BING_NEWS_KEY environment variable.",
            )

        params = {
            "q": query,
            "count": min(limit, 100),
            "mkt": "en-US",
        }

        if from_date:
            params["freshness"] = "Month"

        headers = {"Ocp-Apim-Subscription-Key": self._api_key}
        self.config.headers.update(headers)

        result = await self._get("/news/search", params=params)

        articles = result.get("value", [])
        results = []

        for article in articles:
            pub_date = None
            if article.get("datePublished"):
                try:
                    pub_date = datetime.fromisoformat(
                        article["datePublished"].replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            results.append(
                SearchResult(
                    title=article.get("name", ""),
                    url=article.get("url", ""),
                    snippet=article.get("description", ""),
                    source=article.get("provider", [{}])[0].get("name", "Unknown"),
                    published_date=pub_date,
                    result_type="news",
                )
            )

        response = SearchResponse(
            query=query,
            total_results=result.get("totalEstimatedMatches", len(results)),
            results=results,
            search_engine="bing_news",
        )

        return APIResponse(success=True, data=response.to_dict(), source="websearch")

    async def _search_serpapi_news(
        self,
        query: str,
        from_date: Optional[datetime],
        limit: int,
    ) -> APIResponse:
        """Search using SerpAPI Google News."""
        if not self._api_key:
            return APIResponse(
                success=False,
                error="SerpAPI key not configured. Set SERPAPI_KEY environment variable.",
            )

        params = {
            "engine": "google_news",
            "q": query,
            "gl": "us",
            "hl": "en",
            "api_key": self._api_key,
        }

        result = await self._get("/search", params=params)

        news_results = result.get("news_results", [])
        results = []

        for article in news_results[:limit]:
            pub_date = None
            if article.get("date"):
                try:
                    # SerpAPI dates can be relative ("2 days ago") or absolute
                    date_str = article["date"]
                    if "ago" not in date_str.lower():
                        pub_date = datetime.fromisoformat(date_str)
                except (ValueError, TypeError):
                    pass

            results.append(
                SearchResult(
                    title=article.get("title", ""),
                    url=article.get("link", ""),
                    snippet=article.get("snippet", ""),
                    source=article.get("source", {}).get("name", "Unknown"),
                    published_date=pub_date,
                    result_type="news",
                )
            )

        response = SearchResponse(
            query=query,
            total_results=len(results),
            results=results,
            search_engine="serpapi",
        )

        return APIResponse(success=True, data=response.to_dict(), source="websearch")

    async def search_academic(
        self,
        query: str,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        limit: int = 20,
    ) -> APIResponse:
        """
        Search for academic publications.

        Uses SerpAPI Google Scholar or falls back to CrossRef.

        Args:
            query: Search query
            year_start: Publication year start filter
            year_end: Publication year end filter
            limit: Maximum results

        Returns:
            APIResponse with academic search results
        """
        try:
            if self.preferred_engine == "serpapi" and self._api_key:
                return await self._search_google_scholar(
                    query, year_start, year_end, limit
                )
            else:
                # Fall back to CrossRef (free, no API key needed)
                return await self._search_crossref(query, year_start, year_end, limit)

        except Exception as e:
            logger.error(f"Academic search error for '{query}': {e}")
            return APIResponse(success=False, error=str(e))

    async def _search_google_scholar(
        self,
        query: str,
        year_start: Optional[int],
        year_end: Optional[int],
        limit: int,
    ) -> APIResponse:
        """Search Google Scholar via SerpAPI."""
        params = {
            "engine": "google_scholar",
            "q": query,
            "hl": "en",
            "num": min(limit, 20),
            "api_key": self._api_key,
        }

        if year_start:
            params["as_ylo"] = year_start
        if year_end:
            params["as_yhi"] = year_end

        result = await self._get("/search", params=params)

        organic_results = result.get("organic_results", [])
        results = []

        for article in organic_results:
            pub_info = article.get("publication_info", {})
            authors = pub_info.get("authors", [])

            results.append(
                SearchResult(
                    title=article.get("title", ""),
                    url=article.get("link", ""),
                    snippet=article.get("snippet", ""),
                    source=pub_info.get("summary", ""),
                    authors=[a.get("name", "") for a in authors] if authors else [],
                    result_type="academic",
                )
            )

        response = SearchResponse(
            query=query,
            total_results=result.get("search_information", {}).get(
                "total_results", len(results)
            ),
            results=results,
            search_engine="google_scholar",
        )

        return APIResponse(success=True, data=response.to_dict(), source="websearch")

    async def _search_crossref(
        self,
        query: str,
        year_start: Optional[int],
        year_end: Optional[int],
        limit: int,
    ) -> APIResponse:
        """Search CrossRef for academic publications."""
        # Use CrossRef public API (no key needed)
        crossref_url = "https://api.crossref.org/works"

        params = {
            "query": query,
            "rows": min(limit, 100),
            "sort": "relevance",
        }

        if year_start or year_end:
            date_filter = f"from-pub-date:{year_start or 1900},until-pub-date:{year_end or 2100}"
            params["filter"] = date_filter

        # Make direct HTTP request since this is a different base URL
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(crossref_url, params=params)
            result = response.json()

        items = result.get("message", {}).get("items", [])
        results = []

        for article in items:
            pub_date = None
            if article.get("published-print", {}).get("date-parts"):
                date_parts = article["published-print"]["date-parts"][0]
                if len(date_parts) >= 1:
                    pub_date = datetime(
                        date_parts[0],
                        date_parts[1] if len(date_parts) > 1 else 1,
                        date_parts[2] if len(date_parts) > 2 else 1,
                    )

            authors = []
            for author in article.get("author", []):
                name = f"{author.get('given', '')} {author.get('family', '')}".strip()
                if name:
                    authors.append(name)

            results.append(
                SearchResult(
                    title=article.get("title", [""])[0],
                    url=article.get("URL", ""),
                    snippet=article.get("abstract", "")[:500] if article.get("abstract") else "",
                    source=article.get("container-title", [""])[0],
                    published_date=pub_date,
                    authors=authors,
                    result_type="academic",
                )
            )

        response = SearchResponse(
            query=query,
            total_results=result.get("message", {}).get("total-results", len(results)),
            results=results,
            search_engine="crossref",
        )

        return APIResponse(success=True, data=response.to_dict(), source="websearch")

    async def search_drug_news(
        self,
        drug_name: str,
        include_trials: bool = True,
        include_regulatory: bool = True,
        days_back: int = 30,
        limit: int = 20,
    ) -> APIResponse:
        """
        Search for drug-specific news.

        Combines multiple search queries for comprehensive coverage.

        Args:
            drug_name: Name of the drug
            include_trials: Include clinical trial news
            include_regulatory: Include FDA/EMA news
            days_back: Number of days to search back
            limit: Maximum results per category

        Returns:
            APIResponse with categorized drug news
        """
        from_date = datetime.now() - timedelta(days=days_back)
        all_results = []

        # Main drug news
        main_result = await self.search_news(
            query=drug_name, from_date=from_date, limit=limit
        )
        if main_result.success and main_result.data:
            for result in main_result.data.get("results", []):
                result["category"] = "general"
            all_results.extend(main_result.data.get("results", []))

        # Trial news
        if include_trials:
            trial_result = await self.search_news(
                query=f'"{drug_name}" clinical trial',
                from_date=from_date,
                limit=limit // 2,
            )
            if trial_result.success and trial_result.data:
                for result in trial_result.data.get("results", []):
                    result["category"] = "clinical_trial"
                all_results.extend(trial_result.data.get("results", []))

        # Regulatory news
        if include_regulatory:
            reg_result = await self.search_news(
                query=f'"{drug_name}" (FDA OR EMA OR approval)',
                from_date=from_date,
                limit=limit // 2,
            )
            if reg_result.success and reg_result.data:
                for result in reg_result.data.get("results", []):
                    result["category"] = "regulatory"
                all_results.extend(reg_result.data.get("results", []))

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for result in all_results:
            url = result.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)

        return APIResponse(
            success=True,
            data={
                "drug_name": drug_name,
                "total_results": len(unique_results),
                "results": unique_results[:limit * 2],
                "search_period_days": days_back,
            },
            source="websearch",
        )


# Singleton instance
_websearch_client: Optional[WebSearchClient] = None


async def get_websearch_client(
    cache_manager: Optional[CacheManager] = None,
    preferred_engine: str = "newsapi",
) -> WebSearchClient:
    """Get or create the web search client instance."""
    global _websearch_client

    if _websearch_client is None:
        _websearch_client = WebSearchClient(cache_manager, preferred_engine)

    return _websearch_client
