"""Tests for Journal RSS fetcher and validator with mocked feedparser.

Feature: 011-datasource-integration
Task: T051-T054 — Journal RSS CI source integration

Tests use mocked feedparser so no external network calls are made.
"""

import tempfile
import time
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from dk_data.ingestion.fetchers.journal_rss import (
    DEFAULT_FEEDS,
    JournalRSSFetcher,
)
from dk_data.ingestion.utils.validators import JournalRSSRecord


# ---------------------------------------------------------------------------
# Sample feedparser fixtures
# ---------------------------------------------------------------------------

def _make_entry(**overrides):
    """Build a mock feedparser entry with sensible defaults."""
    base = {
        "title": "A Novel SGLT2 Inhibitor for Heart Failure",
        "link": "https://www.nejm.org/doi/full/10.1056/NEJMoa2026001",
        "summary": "Background: Heart failure remains a leading cause of morbidity.",
        "published_parsed": time.struct_time((2026, 2, 10, 0, 0, 0, 0, 41, 0)),
        "published": "2026-02-10T00:00:00Z",
        "authors": [{"name": "Smith J"}, {"name": "Doe A"}],
        "tags": [{"term": "cardiology"}, {"term": "clinical trial"}],
        "prism_doi": "10.1056/NEJMoa2026001",
        "id": "https://doi.org/10.1056/NEJMoa2026001",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_entry_no_doi(**overrides):
    """Build an entry without DOI — article_id falls back to link."""
    base = {
        "title": "Editorial: Future of Gene Therapy",
        "link": "https://www.bmj.com/content/372/bmj.n123",
        "summary": "Gene therapy continues to advance.",
        "published_parsed": time.struct_time((2026, 1, 15, 0, 0, 0, 0, 15, 0)),
        "published": "2026-01-15T00:00:00Z",
        "id": "https://www.bmj.com/content/372/bmj.n123",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_feed_result(entries, bozo=False, bozo_exception=None):
    """Build a mock feedparser.parse() result."""
    result = SimpleNamespace(
        entries=entries,
        bozo=bozo,
        bozo_exception=bozo_exception,
    )
    return result


# ---------------------------------------------------------------------------
# Fetcher initialisation tests
# ---------------------------------------------------------------------------

class TestJournalRSSFetcherInit:
    """Tests for fetcher initialization."""

    def test_fetcher_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = JournalRSSFetcher(data_dir=tmpdir)
            assert fetcher.SOURCE_NAME == "journal_rss"
            assert fetcher.session is not None

    def test_fetcher_init_defaults(self):
        fetcher = JournalRSSFetcher()
        assert fetcher.SOURCE_NAME == "journal_rss"
        assert fetcher.data_dir.exists()

    def test_get_latest_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = JournalRSSFetcher(data_dir=tmpdir)
            url = fetcher.get_latest_url()
            assert url.startswith("https://")
            assert url == DEFAULT_FEEDS[0]["url"]


# ---------------------------------------------------------------------------
# Fetch with mocked feedparser
# ---------------------------------------------------------------------------

class TestJournalRSSFetch:
    """Tests for the fetch method with mocked feedparser."""

    @patch("dk_data.ingestion.fetchers.journal_rss.feedparser")
    def test_fetch_success(self, mock_feedparser):
        """Full happy-path: feeds return articles."""
        entry1 = _make_entry()
        entry2 = _make_entry(
            title="Immunotherapy Advances in Lung Cancer",
            prism_doi="10.1016/S0140-6736(26)00001-0",
            link="https://www.thelancet.com/doi/10.1016/S0140-6736(26)00001-0",
            id="https://doi.org/10.1016/S0140-6736(26)00001-0",
        )
        entry3 = _make_entry_no_doi()

        mock_feedparser.parse.return_value = _make_feed_result(
            [entry1, entry2, entry3]
        )

        feeds = [
            {"name": "NEJM", "url": "https://www.nejm.org/rss"},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = JournalRSSFetcher(data_dir=tmpdir)
            result = fetcher.fetch(feeds=feeds)

        assert result["status"] == "success"
        assert len(result["records"]) == 3
        assert result["hash"] is not None

        # Verify first article parsed correctly
        rec0 = result["records"][0]
        assert rec0["article_id"] == "10.1056/NEJMoa2026001"
        assert rec0["doi"] == "10.1056/NEJMoa2026001"
        assert rec0["feed_source"] == "NEJM"
        assert rec0["title"] == "A Novel SGLT2 Inhibitor for Heart Failure"
        assert rec0["authors"] == "Smith J; Doe A"
        assert rec0["publication_date"] == "2026-02-10"
        assert rec0["link"] == "https://www.nejm.org/doi/full/10.1056/NEJMoa2026001"
        assert "cardiology" in rec0["categories"]
        assert "clinical trial" in rec0["categories"]

        # Entry without DOI uses link as article_id
        rec2 = result["records"][2]
        assert rec2["article_id"] == "https://www.bmj.com/content/372/bmj.n123"
        assert rec2["doi"] is None

    @patch("dk_data.ingestion.fetchers.journal_rss.feedparser")
    def test_fetch_empty_feed(self, mock_feedparser):
        """Feed returns zero entries."""
        mock_feedparser.parse.return_value = _make_feed_result([])

        feeds = [{"name": "Empty", "url": "https://example.com/rss"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = JournalRSSFetcher(data_dir=tmpdir)
            result = fetcher.fetch(feeds=feeds)

        assert result["status"] == "success"
        assert result["records"] == []
        assert result["hash"] is None

    @patch("dk_data.ingestion.fetchers.journal_rss.feedparser")
    def test_fetch_bozo_error(self, mock_feedparser):
        """Feed with bozo error and no entries returns empty gracefully."""
        mock_feedparser.parse.return_value = _make_feed_result(
            [], bozo=True, bozo_exception=Exception("Malformed XML")
        )

        feeds = [{"name": "Bad", "url": "https://example.com/bad-rss"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = JournalRSSFetcher(data_dir=tmpdir)
            result = fetcher.fetch(feeds=feeds)

        assert result["status"] == "success"
        assert result["records"] == []

    @patch("dk_data.ingestion.fetchers.journal_rss.feedparser")
    def test_fetch_deduplication(self, mock_feedparser):
        """Duplicate entries (same DOI) across feeds are deduplicated."""
        entry = _make_entry()

        # Two feeds return the same article
        mock_feedparser.parse.return_value = _make_feed_result([entry])

        feeds = [
            {"name": "Feed1", "url": "https://example.com/rss1"},
            {"name": "Feed2", "url": "https://example.com/rss2"},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = JournalRSSFetcher(data_dir=tmpdir)
            result = fetcher.fetch(feeds=feeds)

        assert result["status"] == "success"
        # Same DOI should be deduplicated
        assert len(result["records"]) == 1

    @patch("dk_data.ingestion.fetchers.journal_rss.feedparser")
    def test_fetch_multiple_feeds(self, mock_feedparser):
        """Fetch aggregates entries from multiple feeds."""
        entry1 = _make_entry()
        entry2 = _make_entry(
            title="Different Article",
            prism_doi="10.1001/jama.2026.0001",
            link="https://jamanetwork.com/article/1",
            id="https://doi.org/10.1001/jama.2026.0001",
        )

        call_count = 0

        def side_effect(url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_feed_result([entry1])
            return _make_feed_result([entry2])

        mock_feedparser.parse.side_effect = side_effect

        feeds = [
            {"name": "NEJM", "url": "https://www.nejm.org/rss"},
            {"name": "JAMA", "url": "https://jamanetwork.com/rss"},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = JournalRSSFetcher(data_dir=tmpdir)
            result = fetcher.fetch(feeds=feeds)

        assert result["status"] == "success"
        assert len(result["records"]) == 2

    @patch("dk_data.ingestion.fetchers.journal_rss.feedparser")
    def test_fetch_feed_exception_handled(self, mock_feedparser):
        """Individual feed failures do not crash the overall fetch."""
        mock_feedparser.parse.side_effect = Exception("Network error")

        feeds = [{"name": "Broken", "url": "https://example.com/broken"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = JournalRSSFetcher(data_dir=tmpdir)
            result = fetcher.fetch(feeds=feeds)

        assert result["status"] == "success"
        assert result["records"] == []

    @patch("dk_data.ingestion.fetchers.journal_rss.feedparser")
    def test_fetch_default_feeds_fallback(self, mock_feedparser):
        """When _get_feeds raises, defaults are used."""
        mock_feedparser.parse.return_value = _make_feed_result([])

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = JournalRSSFetcher(data_dir=tmpdir)
            # Patch _get_feeds to simulate DB failure -> defaults
            with patch.object(
                fetcher, "_get_feeds", return_value=DEFAULT_FEEDS[:2]
            ):
                result = fetcher.fetch()

        assert result["status"] == "success"
        # feedparser.parse was called for each feed
        assert mock_feedparser.parse.call_count == 2


# ---------------------------------------------------------------------------
# Entry parsing unit tests
# ---------------------------------------------------------------------------

class TestEntryParsing:
    """Tests for low-level entry normalization helpers."""

    def test_extract_doi_from_prism(self):
        entry = SimpleNamespace(prism_doi="10.1056/NEJMoa2026001")
        doi = JournalRSSFetcher._extract_doi(entry)
        assert doi == "10.1056/NEJMoa2026001"

    def test_extract_doi_from_id(self):
        entry = SimpleNamespace(id="https://doi.org/10.1038/s41586-026-00001")
        doi = JournalRSSFetcher._extract_doi(entry)
        assert doi == "10.1038/s41586-026-00001"

    def test_extract_doi_none(self):
        entry = SimpleNamespace(id="not-a-doi-link")
        doi = JournalRSSFetcher._extract_doi(entry)
        assert doi is None

    def test_parse_entry_date_structured(self):
        entry = SimpleNamespace(
            published_parsed=time.struct_time((2026, 3, 1, 0, 0, 0, 0, 60, 0)),
        )
        result = JournalRSSFetcher._parse_entry_date(entry)
        assert result == "2026-03-01"

    def test_parse_entry_date_string_fallback(self):
        entry = SimpleNamespace(
            published="2026-01-15T10:00:00Z",
        )
        result = JournalRSSFetcher._parse_entry_date(entry)
        assert result == "2026-01-15"

    def test_parse_entry_date_none(self):
        entry = SimpleNamespace()
        result = JournalRSSFetcher._parse_entry_date(entry)
        assert result is None

    def test_extract_authors_list(self):
        entry = SimpleNamespace(
            authors=[{"name": "Alice"}, {"name": "Bob"}]
        )
        result = JournalRSSFetcher._extract_authors(entry)
        assert result == "Alice; Bob"

    def test_extract_authors_single(self):
        entry = SimpleNamespace(author="Jane Doe")
        result = JournalRSSFetcher._extract_authors(entry)
        assert result == "Jane Doe"

    def test_extract_authors_none(self):
        entry = SimpleNamespace()
        result = JournalRSSFetcher._extract_authors(entry)
        assert result is None


# ---------------------------------------------------------------------------
# JournalRSSRecord validator tests
# ---------------------------------------------------------------------------

class TestJournalRSSRecord:
    """Tests for the JournalRSSRecord Pydantic model."""

    def test_valid_record(self):
        record = JournalRSSRecord(
            article_id="10.1056/NEJMoa2026001",
            feed_source="NEJM",
            title="Test Article",
            authors="Smith J; Doe A",
            abstract="Background text here.",
            publication_date=date(2026, 2, 10),
            link="https://www.nejm.org/doi/full/10.1056/NEJMoa2026001",
            doi="10.1056/NEJMoa2026001",
            categories=["cardiology", "clinical trial"],
        )
        assert record.article_id == "10.1056/NEJMoa2026001"
        assert record.feed_source == "NEJM"
        assert record.title == "Test Article"
        assert len(record.categories) == 2

    def test_minimal_record(self):
        record = JournalRSSRecord(
            article_id="https://example.com/article/1",
            feed_source="Example Journal",
        )
        assert record.article_id == "https://example.com/article/1"
        assert record.title is None
        assert record.doi is None
        assert record.categories is None

    def test_empty_article_id_rejected(self):
        with pytest.raises(ValidationError):
            JournalRSSRecord(article_id="", feed_source="Test")

    def test_missing_article_id_rejected(self):
        with pytest.raises(ValidationError):
            JournalRSSRecord(feed_source="Test")

    def test_empty_feed_source_rejected(self):
        with pytest.raises(ValidationError):
            JournalRSSRecord(article_id="some-id", feed_source="")

    def test_missing_feed_source_rejected(self):
        with pytest.raises(ValidationError):
            JournalRSSRecord(article_id="some-id")

    def test_whitespace_stripped(self):
        record = JournalRSSRecord(
            article_id="  10.1056/test  ",
            feed_source="  NEJM  ",
        )
        assert record.article_id == "10.1056/test"
        assert record.feed_source == "NEJM"
