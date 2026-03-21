"""Journal RSS Feed Fetcher.

Feature: 011-datasource-integration
Task: T051-T054 — Journal RSS CI source integration

Fetches recent articles from major pharmaceutical/medical journal RSS
feeds using the feedparser library.  Feed URLs are read from
meta.ops_ci_search_terms (term_type='journal_feed'); a built-in default
list is used as a fallback when no DB rows are found.

Daily cadence, deduplicates on article DOI or URL (stored as article_id).
"""

import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import feedparser

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Default RSS feeds for major pharmaceutical/medical journals.
# Used when meta.ops_ci_search_terms has no 'journal_feed' rows.
DEFAULT_FEEDS: List[Dict[str, str]] = [
    {
        "name": "NEJM",
        "url": "https://www.nejm.org/action/showFeed?jc=nejm&type=etoc&feed=rss",
    },
    {
        "name": "Lancet",
        "url": "https://www.thelancet.com/rssfeed/lancet_current.xml",
    },
    {
        "name": "JAMA",
        "url": "https://jamanetwork.com/rss/site_3/67.xml",
    },
    {
        "name": "BMJ",
        "url": "https://www.bmj.com/rss/recent.xml",
    },
    {
        "name": "Nature Medicine",
        "url": "https://www.nature.com/nm.rss",
    },
    {
        "name": "Nature Reviews Drug Discovery",
        "url": "https://www.nature.com/nrd.rss",
    },
    {
        "name": "Lancet Oncology",
        "url": "https://www.thelancet.com/rssfeed/lanonc_current.xml",
    },
    {
        "name": "JAMA Oncology",
        "url": "https://jamanetwork.com/rss/site_3/191.xml",
    },
]


class JournalRSSFetcher(BaseFetcher):
    """Fetcher for journal RSS feeds (CI scope)."""

    SOURCE_NAME = "journal_rss"
    BASE_URL = ""  # Multiple feeds; no single base URL

    def get_latest_url(self) -> str:
        """Return a representative URL (first default feed)."""
        return DEFAULT_FEEDS[0]["url"]

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch articles from configured journal RSS feeds.

        Keyword Args:
            feeds: Optional list of feed dicts with 'name' and 'url' keys.
                   If not provided, reads from DB or falls back to defaults.

        Returns:
            Dict with keys: status, records, hash, error (on failure).
        """
        try:
            feeds = kwargs.get("feeds") or self._get_feeds()

            if not feeds:
                logger.warning("No journal RSS feeds configured")
                result: Dict[str, Any] = {
                    "status": "success",
                    "records": [],
                    "hash": None,
                    "message": "No feeds configured",
                }
                self.log_fetch_result(result)
                return result

            logger.info("Fetching articles from %d RSS feeds", len(feeds))

            all_records: List[Dict[str, Any]] = []
            seen_ids: set = set()

            for feed_info in feeds:
                feed_name = feed_info["name"]
                feed_url = feed_info["url"]

                try:
                    entries = self._parse_feed(feed_url, feed_name)
                    for entry in entries:
                        article_id = entry.get("article_id")
                        if article_id and article_id not in seen_ids:
                            seen_ids.add(article_id)
                            all_records.append(entry)
                except Exception as e:
                    logger.warning(
                        "Failed to parse feed %s (%s): %s",
                        feed_name, feed_url, e,
                    )
                    continue

            # Compute content hash
            content_hash = hashlib.md5(
                ",".join(sorted(seen_ids)).encode()
            ).hexdigest() if seen_ids else None

            result = {
                "status": "success",
                "records": all_records,
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(all_records)})
            return result

        except Exception as e:
            logger.exception("Journal RSS fetch failed: %s", e)
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

    def _get_feeds(self) -> List[Dict[str, str]]:
        """Read feed URLs from meta.ops_ci_search_terms or fall back to defaults.

        Returns:
            List of dicts with 'name' and 'url' keys.
        """
        try:
            from ..utils.database import get_connection

            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT term_value
                        FROM meta.ops_ci_search_terms
                        WHERE term_type = 'journal_feed'
                          AND is_active = TRUE
                        ORDER BY term_id
                        """
                    )
                    rows = cur.fetchall()

            if rows:
                feeds = []
                for row in rows:
                    url = row[0]
                    # Derive a short name from the hostname
                    parsed = urlparse(url)
                    name = parsed.hostname or "unknown"
                    feeds.append({"name": name, "url": url})
                logger.info(
                    "Loaded %d journal feed URLs from meta.ops_ci_search_terms",
                    len(feeds),
                )
                return feeds

        except Exception as e:
            logger.warning(
                "Could not read journal feeds from DB, using defaults: %s", e
            )

        logger.info("Using %d default journal RSS feeds", len(DEFAULT_FEEDS))
        return list(DEFAULT_FEEDS)

    def _parse_feed(
        self, feed_url: str, feed_name: str
    ) -> List[Dict[str, Any]]:
        """Parse a single RSS feed and return normalized records.

        Args:
            feed_url: RSS feed URL.
            feed_name: Human-readable feed name.

        Returns:
            List of record dicts matching raw.journal_rss schema.
        """
        logger.debug("Parsing RSS feed: %s (%s)", feed_name, feed_url)
        parsed = feedparser.parse(feed_url)

        if parsed.bozo and not parsed.entries:
            logger.warning(
                "Feed %s returned bozo error: %s",
                feed_name, parsed.bozo_exception,
            )
            return []

        records: List[Dict[str, Any]] = []

        for entry in parsed.entries:
            record = self._normalize_entry(entry, feed_name)
            if record:
                records.append(record)

        logger.info("Parsed %d entries from %s", len(records), feed_name)
        return records

    def _normalize_entry(
        self, entry: Any, feed_name: str
    ) -> Optional[Dict[str, Any]]:
        """Normalize a single feedparser entry to the raw.journal_rss schema.

        Uses DOI as article_id when available; otherwise falls back to the
        entry link URL.

        Returns:
            Record dict, or None if no usable identifier is found.
        """
        # Extract DOI (often in prism_doi, dc_identifier, or id)
        doi = self._extract_doi(entry)

        link = getattr(entry, "link", None)

        # Build a stable article_id: prefer DOI, fall back to link
        if doi:
            article_id = doi
        elif link:
            article_id = link
        else:
            return None

        # Publication date
        pub_date = self._parse_entry_date(entry)

        # Authors
        authors = self._extract_authors(entry)

        # Abstract / summary
        abstract = None
        if hasattr(entry, "summary"):
            abstract = entry.summary
        elif hasattr(entry, "description"):
            abstract = entry.description

        # Categories / tags
        categories = None
        if hasattr(entry, "tags"):
            categories = [
                tag.get("term", "") for tag in entry.tags if tag.get("term")
            ]

        return {
            "article_id": article_id,
            "feed_source": feed_name,
            "title": getattr(entry, "title", None),
            "authors": authors,
            "abstract": abstract,
            "publication_date": pub_date,
            "link": link,
            "doi": doi,
            "categories": categories,
        }

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_doi(entry: Any) -> Optional[str]:
        """Extract DOI from various feedparser entry fields."""
        # Common RSS/Atom DOI fields
        for attr in ("prism_doi", "dc_identifier", "doi"):
            val = getattr(entry, attr, None)
            if val and isinstance(val, str) and val.strip().startswith("10."):
                return val.strip()

        # Try extracting from id field
        entry_id = getattr(entry, "id", "")
        if isinstance(entry_id, str) and "10." in entry_id:
            # e.g. "https://doi.org/10.1056/NEJMoa2026372"
            idx = entry_id.find("10.")
            candidate = entry_id[idx:]
            if len(candidate) > 5:
                return candidate

        return None

    @staticmethod
    def _parse_entry_date(entry: Any) -> Optional[str]:
        """Extract publication date as YYYY-MM-DD string."""
        # feedparser normalizes dates into *_parsed tuples
        for attr in ("published_parsed", "updated_parsed"):
            time_struct = getattr(entry, attr, None)
            if time_struct:
                try:
                    dt = datetime(*time_struct[:6])
                    return dt.strftime("%Y-%m-%d")
                except (TypeError, ValueError):
                    continue

        # Fallback: raw date strings
        for attr in ("published", "updated"):
            raw = getattr(entry, attr, None)
            if raw:
                try:
                    return raw[:10]  # best-effort YYYY-MM-DD
                except Exception:
                    continue

        return None

    @staticmethod
    def _extract_authors(entry: Any) -> Optional[str]:
        """Extract author string from a feedparser entry."""
        # Some feeds have an 'authors' list
        if hasattr(entry, "authors") and entry.authors:
            names = [
                a.get("name", "") for a in entry.authors if a.get("name")
            ]
            if names:
                return "; ".join(names)

        # Fallback to 'author' field
        author = getattr(entry, "author", None)
        if author:
            return author

        return None
