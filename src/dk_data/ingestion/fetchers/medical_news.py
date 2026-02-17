"""Medical News RSS/API Fetcher.

Feature: 011-datasource-integration
Task: T067-T069 — Medical news aggregation

Fetches medical and pharmaceutical news from multiple RSS sources
including Medscape, Healio, and FiercePharma. Uses feedparser for
RSS parsing and extracts drug mentions from article text.

Sources:
- Medscape: https://www.medscape.com/cx/rssfeeds/index
- Healio: https://www.healio.com/rss
- FiercePharma: https://www.fiercepharma.com/rss/xml
"""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import feedparser

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# RSS feed sources
DEFAULT_RSS_FEEDS = {
    "medscape": "https://www.medscape.com/cx/rssfeeds/2286.xml",
    "healio": "https://www.healio.com/rss/pharmacy",
    "fiercepharma": "https://www.fiercepharma.com/rss/xml",
}

# Max records per fetch run
MAX_RECORDS = 5000


class MedicalNewsFetcher(BaseFetcher):
    """Fetcher for medical news from multiple RSS feeds."""

    SOURCE_NAME = "medical_news"
    BASE_URL = "https://www.medscape.com"

    def __init__(self, data_dir: Optional[str] = None):
        """Initialize the medical news fetcher."""
        super().__init__(data_dir)

        self.session.headers.update({
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
            "User-Agent": "DK-Data-Platform/1.0 (Medical News Aggregator)",
        })

        # Drug names for mention detection (loaded from DB or defaults)
        self._drug_names: Optional[List[str]] = None

    def get_latest_url(self) -> str:
        """Get the primary RSS feed URL."""
        return DEFAULT_RSS_FEEDS.get("medscape", self.BASE_URL)

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch medical news from RSS feeds.

        Keyword Args:
            feeds: Dict of source_name -> RSS URL (default: DEFAULT_RSS_FEEDS).
            max_records: Maximum records to fetch (default: 5000).
            days_back: Number of days to look back (default: 7).

        Returns:
            Dict with status, records, hash, error.
        """
        feeds = kwargs.get("feeds", DEFAULT_RSS_FEEDS)
        max_records = kwargs.get("max_records", MAX_RECORDS)
        days_back = kwargs.get("days_back", 7)

        try:
            # Load drug names for mention detection
            drug_names = self._load_drug_names()

            logger.info(
                "Fetching medical news (feeds=%d, days_back=%d, drug_names=%d)",
                len(feeds), days_back, len(drug_names),
            )

            all_records: List[Dict[str, Any]] = []
            seen_ids: set = set()
            cutoff_date = datetime.utcnow() - timedelta(days=days_back)

            for source_name, feed_url in feeds.items():
                if len(all_records) >= max_records:
                    break

                try:
                    records = self._fetch_feed(
                        source_name, feed_url,
                        cutoff_date=cutoff_date,
                        drug_names=drug_names,
                    )

                    for rec in records:
                        article_id = rec.get("article_id")
                        if article_id and article_id not in seen_ids:
                            seen_ids.add(article_id)
                            all_records.append(rec)

                except Exception as e:
                    logger.warning("Failed to fetch feed %s: %s", source_name, e)
                    continue

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
            logger.exception("Failed to fetch medical news: %s", e)
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
    # Feed processing
    # ------------------------------------------------------------------

    def _fetch_feed(
        self,
        source_name: str,
        feed_url: str,
        *,
        cutoff_date: datetime,
        drug_names: List[str],
    ) -> List[Dict[str, Any]]:
        """Fetch and parse a single RSS feed."""
        logger.debug("Fetching RSS feed: %s (%s)", source_name, feed_url)

        response = self.session.get(feed_url, timeout=30)
        response.raise_for_status()

        feed = feedparser.parse(response.content)

        if feed.bozo and not feed.entries:
            logger.warning("Feed %s returned bozo (malformed): %s", source_name, feed.bozo_exception)
            return []

        records: List[Dict[str, Any]] = []

        for entry in feed.entries:
            record = self._parse_entry(entry, source_name, cutoff_date, drug_names)
            if record:
                records.append(record)

        logger.info("Parsed %d articles from %s", len(records), source_name)
        return records

    def _parse_entry(
        self,
        entry: Any,
        source_name: str,
        cutoff_date: datetime,
        drug_names: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Parse a single RSS feed entry into a record dict."""
        title = getattr(entry, "title", None)
        link = getattr(entry, "link", None)
        summary = getattr(entry, "summary", None) or getattr(entry, "description", None)

        if not title and not link:
            return None

        # Generate unique article_id from source + URL
        article_id = self._generate_article_id(source_name, link or title)

        # Parse publication date
        pub_date = self._parse_pub_date(entry)

        # Filter by date
        if pub_date and cutoff_date:
            try:
                pub_dt = datetime.strptime(pub_date, "%Y-%m-%d")
                if pub_dt < cutoff_date:
                    return None
            except (ValueError, TypeError):
                pass

        # Extract drug mentions from title and summary
        text_content = f"{title or ''} {summary or ''}"
        drug_mentions = self._extract_drug_mentions(text_content, drug_names)

        # Extract therapeutic areas from feed categories/tags
        therapeutic_areas = self._extract_therapeutic_areas(entry)

        return {
            "article_id": article_id,
            "source_name": source_name,
            "title": title,
            "summary": self._clean_html(summary) if summary else None,
            "publication_date": pub_date,
            "url": link,
            "drug_mentions": drug_mentions if drug_mentions else None,
            "therapeutic_areas": therapeutic_areas if therapeutic_areas else None,
        }

    @staticmethod
    def _generate_article_id(source_name: str, url_or_title: str) -> str:
        """Generate a unique article ID from source and URL hash."""
        content = f"{source_name}:{url_or_title}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    @staticmethod
    def _parse_pub_date(entry: Any) -> Optional[str]:
        """Parse publication date from RSS entry."""
        # Try published_parsed first (struct_time)
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                dt = datetime(*entry.published_parsed[:6])
                return dt.strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                pass

        # Try updated_parsed
        if hasattr(entry, "updated_parsed") and entry.updated_parsed:
            try:
                dt = datetime(*entry.updated_parsed[:6])
                return dt.strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                pass

        # Try string dates
        for attr in ("published", "updated", "date"):
            val = getattr(entry, attr, None)
            if val:
                try:
                    # feedparser often provides dates as strings
                    return str(val)[:10]
                except (TypeError, ValueError):
                    pass

        return None

    @staticmethod
    def _extract_drug_mentions(
        text: str, drug_names: List[str]
    ) -> List[str]:
        """Extract drug name mentions from text."""
        if not text or not drug_names:
            return []

        text_lower = text.lower()
        found: List[str] = []

        for drug in drug_names:
            if drug.lower() in text_lower:
                found.append(drug)

        return sorted(set(found))

    @staticmethod
    def _extract_therapeutic_areas(entry: Any) -> List[str]:
        """Extract therapeutic area tags from RSS entry."""
        areas: List[str] = []

        # Check tags/categories
        tags = getattr(entry, "tags", [])
        for tag in tags:
            term = getattr(tag, "term", None)
            if term:
                areas.append(term)

        # Check category
        category = getattr(entry, "category", None)
        if category:
            areas.append(category)

        return sorted(set(areas))

    @staticmethod
    def _clean_html(text: str) -> str:
        """Remove HTML tags from text."""
        import re
        clean = re.sub(r"<[^>]+>", "", text)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    # ------------------------------------------------------------------
    # Drug names from database
    # ------------------------------------------------------------------

    def _load_drug_names(self) -> List[str]:
        """Load active drug_name values from meta.ci_search_terms."""
        if self._drug_names is not None:
            return self._drug_names

        try:
            from ..utils.database import get_connection

            names: List[str] = []
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT term_value
                        FROM meta.ci_search_terms
                        WHERE term_type = 'drug_name'
                          AND is_active = TRUE
                        ORDER BY term_value
                        """
                    )
                    for row in cur.fetchall():
                        names.append(row[0])

            logger.info("Loaded %d drug names from meta.ci_search_terms", len(names))
            self._drug_names = names
            return names

        except Exception as e:
            logger.warning("Could not load drug names from DB: %s", e)
            self._drug_names = []
            return []
