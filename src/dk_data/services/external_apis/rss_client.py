"""
RSS Feed Client for regulatory news and company updates.

Implements T141: RSSFeedClient class.

Monitors RSS feeds from:
- FDA Press Releases
- EMA News
- SEC EDGAR (company filings)
- Company IR (investor relations) feeds
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List, Dict, Any
import aiohttp
import xml.etree.ElementTree as ET
from loguru import logger

from .base_client import BaseAPIClient, APIClientConfig


@dataclass
class FeedItem:
    """RSS feed item/article."""
    title: str
    link: str
    source: str
    published_date: Optional[datetime] = None
    description: Optional[str] = None
    category: Optional[str] = None
    guid: Optional[str] = None
    author: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "title": self.title,
            "link": self.link,
            "source": self.source,
            "published_date": self.published_date.isoformat() if self.published_date else None,
            "description": self.description[:500] if self.description else None,
            "category": self.category,
            "author": self.author,
        }


class RSSFeedClient(BaseAPIClient):
    """
    Client for monitoring RSS feeds from regulatory agencies and companies.

    Feed Sources:
    - FDA: Press releases, drug approvals, safety communications
    - EMA: News, product updates
    - SEC EDGAR: Company 8-K, 10-K filings
    - Company IR: Press releases from pharma companies
    """

    # Regulatory RSS feeds
    FEEDS = {
        "fda_press": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml",
        "fda_drugs": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/drugs/rss.xml",
        "fda_safety": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/medwatch/rss.xml",
        "ema_news": "https://www.ema.europa.eu/en/feeds/news.xml",
        "ema_medicines": "https://www.ema.europa.eu/en/feeds/medicines.xml",
    }

    # Major pharma company IR feeds (examples)
    COMPANY_FEEDS = {
        "pfizer": "https://www.pfizer.com/rss/news.xml",
        "merck": "https://www.merck.com/news/rss/press_releases.xml",
        "novartis": "https://www.novartis.com/news/rss.xml",
        "roche": "https://www.roche.com/media/rss-feeds.xml",
        "jnj": "https://www.jnj.com/news/rss",
        "bms": "https://news.bms.com/rss/news-releases.xml",
        "astrazeneca": "https://www.astrazeneca.com/media-centre/rss-feeds.xml",
        "gsk": "https://www.gsk.com/en-gb/media/rss-feed/",
        "sanofi": "https://www.sanofi.com/en/media-room/rss",
        "abbvie": "https://news.abbvie.com/rss/news-releases.xml",
    }

    def __init__(self, cache_ttl: int = 900):  # 15 minute cache
        config = APIClientConfig(
            base_url="",  # RSS feeds use full URLs
            requests_per_second=2.0,  # 2 requests per second
            cache_ttl=cache_ttl,
        )
        super().__init__(config)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def fetch_feed(
        self,
        feed_url: str,
        source_name: str = "unknown",
        limit: int = 50,
    ) -> List[FeedItem]:
        """
        Fetch and parse an RSS feed.

        Args:
            feed_url: URL of the RSS feed
            source_name: Name to identify the source
            limit: Maximum items to return

        Returns:
            List of feed items
        """
        logger.debug(f"Fetching RSS feed: {feed_url}")

        try:
            session = await self._get_session()

            async with session.get(
                feed_url,
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"User-Agent": "Mozilla/5.0 (compatible; GroundTruthBot/1.0)"},
            ) as response:
                if response.status != 200:
                    logger.warning(f"RSS feed returned {response.status}: {feed_url}")
                    return []

                content = await response.text()
                return self._parse_rss(content, source_name, limit)

        except Exception as e:
            logger.error(f"Error fetching RSS feed {feed_url}: {e}")
            return []

    def _parse_rss(
        self,
        content: str,
        source_name: str,
        limit: int,
    ) -> List[FeedItem]:
        """Parse RSS XML content."""
        items = []

        try:
            root = ET.fromstring(content)

            # Handle different RSS formats
            # RSS 2.0
            for item in root.findall(".//item")[:limit]:
                items.append(self._parse_item(item, source_name))

            # Atom format
            if not items:
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                for entry in root.findall(".//atom:entry", ns)[:limit]:
                    items.append(self._parse_atom_entry(entry, source_name, ns))

        except ET.ParseError as e:
            logger.error(f"Error parsing RSS XML: {e}")

        return items

    def _parse_item(self, item: ET.Element, source_name: str) -> FeedItem:
        """Parse RSS 2.0 item element."""
        title = item.findtext("title", "")
        link = item.findtext("link", "")
        description = item.findtext("description", "")
        pub_date = item.findtext("pubDate")
        category = item.findtext("category")
        guid = item.findtext("guid")
        author = item.findtext("author") or item.findtext("dc:creator")

        # Parse date
        published = None
        if pub_date:
            published = self._parse_date(pub_date)

        return FeedItem(
            title=title,
            link=link,
            source=source_name,
            published_date=published,
            description=self._clean_html(description),
            category=category,
            guid=guid,
            author=author,
        )

    def _parse_atom_entry(
        self,
        entry: ET.Element,
        source_name: str,
        ns: Dict[str, str],
    ) -> FeedItem:
        """Parse Atom entry element."""
        title = entry.findtext("atom:title", "", ns)

        # Get link - try different approaches
        link = ""
        link_elem = entry.find("atom:link[@rel='alternate']", ns)
        if link_elem is not None:
            link = link_elem.get("href", "")
        else:
            link_elem = entry.find("atom:link", ns)
            if link_elem is not None:
                link = link_elem.get("href", "")

        summary = entry.findtext("atom:summary", "", ns)
        updated = entry.findtext("atom:updated", "", ns)
        entry_id = entry.findtext("atom:id", "", ns)

        published = None
        if updated:
            published = self._parse_date(updated)

        return FeedItem(
            title=title,
            link=link,
            source=source_name,
            published_date=published,
            description=self._clean_html(summary),
            guid=entry_id,
        )

    async def get_fda_news(self, limit: int = 20) -> List[FeedItem]:
        """Get recent FDA news and press releases."""
        items = []

        for feed_name in ["fda_press", "fda_drugs", "fda_safety"]:
            feed_url = self.FEEDS.get(feed_name)
            if feed_url:
                feed_items = await self.fetch_feed(feed_url, feed_name, limit // 3)
                items.extend(feed_items)

        # Sort by date
        items.sort(key=lambda x: x.published_date or datetime.min, reverse=True)
        return items[:limit]

    async def get_ema_news(self, limit: int = 20) -> List[FeedItem]:
        """Get recent EMA news."""
        items = []

        for feed_name in ["ema_news", "ema_medicines"]:
            feed_url = self.FEEDS.get(feed_name)
            if feed_url:
                feed_items = await self.fetch_feed(feed_url, feed_name, limit // 2)
                items.extend(feed_items)

        items.sort(key=lambda x: x.published_date or datetime.min, reverse=True)
        return items[:limit]

    async def get_company_news(
        self,
        companies: Optional[List[str]] = None,
        limit: int = 50,
    ) -> List[FeedItem]:
        """
        Get news from pharma company IR feeds.

        Args:
            companies: List of company keys (e.g., ["pfizer", "merck"])
                       If None, fetches from all known companies
            limit: Maximum items per company

        Returns:
            Combined list of company news
        """
        if companies is None:
            companies = list(self.COMPANY_FEEDS.keys())

        items = []
        for company in companies:
            feed_url = self.COMPANY_FEEDS.get(company.lower())
            if feed_url:
                try:
                    company_items = await self.fetch_feed(
                        feed_url, company, limit // len(companies)
                    )
                    items.extend(company_items)
                except Exception as e:
                    logger.warning(f"Failed to fetch {company} feed: {e}")

        items.sort(key=lambda x: x.published_date or datetime.min, reverse=True)
        return items[:limit]

    async def search_news(
        self,
        query: str,
        sources: Optional[List[str]] = None,
        limit: int = 50,
    ) -> List[FeedItem]:
        """
        Search for news items matching a query.

        Args:
            query: Search term (drug name, company, etc.)
            sources: List of sources to search (e.g., ["fda_press", "pfizer"])
            limit: Maximum results

        Returns:
            Matching news items
        """
        if sources is None:
            sources = list(self.FEEDS.keys()) + list(self.COMPANY_FEEDS.keys())

        all_items = []

        for source in sources:
            feed_url = self.FEEDS.get(source) or self.COMPANY_FEEDS.get(source)
            if feed_url:
                items = await self.fetch_feed(feed_url, source, 50)
                all_items.extend(items)

        # Filter by query
        query_lower = query.lower()
        filtered = [
            item for item in all_items
            if query_lower in item.title.lower()
            or (item.description and query_lower in item.description.lower())
        ]

        filtered.sort(key=lambda x: x.published_date or datetime.min, reverse=True)
        return filtered[:limit]

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string from RSS feed."""
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",  # RFC 822
            "%a, %d %b %Y %H:%M:%S %Z",
            "%Y-%m-%dT%H:%M:%S%z",  # ISO 8601
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        return None

    def _clean_html(self, text: Optional[str]) -> Optional[str]:
        """Remove HTML tags from text."""
        if not text:
            return None

        import re
        clean = re.sub(r'<[^>]+>', '', text)
        clean = clean.replace('&nbsp;', ' ')
        clean = clean.replace('&amp;', '&')
        clean = clean.replace('&lt;', '<')
        clean = clean.replace('&gt;', '>')
        return clean.strip()

    async def close(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def health_check(self) -> bool:
        """Check if RSS feeds are accessible."""
        try:
            session = await self._get_session()
            async with session.get(
                self.FEEDS["fda_press"],
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                return response.status < 500
        except Exception:
            return False
