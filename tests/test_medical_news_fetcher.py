"""Tests for Medical News RSS Fetcher and MedicalNewsRecord validator.

Feature: 011-datasource-integration
Task: T067-T069 — Medical news aggregation

Tests cover:
- Fetcher initialization
- get_latest_url endpoint
- Full fetch with mocked RSS feeds
- RSS entry parsing and normalization
- Drug mention extraction
- Article ID generation
- HTML cleaning
- MedicalNewsRecord validation (valid and invalid)
"""

import tempfile
import time
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import responses

from dk_data.ingestion.fetchers.medical_news import (
    MedicalNewsFetcher,
    DEFAULT_RSS_FEEDS,
)
from dk_data.ingestion.utils.validators import MedicalNewsRecord


# ---------------------------------------------------------------------------
# Sample RSS feed fixtures
# ---------------------------------------------------------------------------

SAMPLE_RSS_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Medscape Medical News</title>
    <link>https://www.medscape.com</link>
    <item>
      <title>New Drug Keytruda Shows Promise in Lung Cancer Trial</title>
      <link>https://www.medscape.com/viewarticle/12345</link>
      <description>&lt;p&gt;A new clinical trial demonstrates that Keytruda significantly improves survival.&lt;/p&gt;</description>
      <pubDate>Mon, 10 Feb 2026 12:00:00 GMT</pubDate>
      <category>Oncology</category>
    </item>
    <item>
      <title>FDA Approves Humira Biosimilar</title>
      <link>https://www.medscape.com/viewarticle/12346</link>
      <description>The FDA has approved a new biosimilar for Humira.</description>
      <pubDate>Tue, 11 Feb 2026 14:00:00 GMT</pubDate>
      <category>Rheumatology</category>
    </item>
  </channel>
</rss>
"""

SAMPLE_RSS_EMPTY = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Empty Feed</title>
    <link>https://example.com</link>
  </channel>
</rss>
"""


# ---------------------------------------------------------------------------
# Fetcher tests: initialization
# ---------------------------------------------------------------------------

class TestMedicalNewsFetcherInit:
    """Tests for Medical News fetcher initialization."""

    def test_fetcher_init(self, tmp_path):
        """Verify fetcher initializes with correct source name."""
        fetcher = MedicalNewsFetcher(data_dir=str(tmp_path))
        assert fetcher.SOURCE_NAME == "medical_news"
        assert fetcher.session is not None
        assert fetcher.data_dir == tmp_path

    def test_fetcher_accepts_rss(self, tmp_path):
        """Verify the Accept header includes RSS content types."""
        fetcher = MedicalNewsFetcher(data_dir=str(tmp_path))
        accept = fetcher.session.headers.get("Accept", "")
        assert "xml" in accept.lower()


# ---------------------------------------------------------------------------
# Fetcher tests: get_latest_url
# ---------------------------------------------------------------------------

class TestMedicalNewsFetcherURL:
    """Tests for get_latest_url."""

    def test_get_latest_url(self, tmp_path):
        """Verify get_latest_url returns a valid URL."""
        fetcher = MedicalNewsFetcher(data_dir=str(tmp_path))
        url = fetcher.get_latest_url()
        assert url.startswith("https://")


# ---------------------------------------------------------------------------
# Fetcher tests: fetch with mocked HTTP
# ---------------------------------------------------------------------------

class TestMedicalNewsFetcherFetch:
    """Tests for the fetch method with mocked HTTP responses."""

    @responses.activate
    def test_fetch_success(self, tmp_path):
        """Test complete fetch with mocked RSS feeds."""
        test_feed_url = "https://test.example.com/rss.xml"
        responses.add(
            responses.GET,
            test_feed_url,
            body=SAMPLE_RSS_XML.encode(),
            status=200,
            content_type="application/rss+xml",
        )

        fetcher = MedicalNewsFetcher(data_dir=str(tmp_path))
        # Bypass DB loading of drug names
        fetcher._drug_names = ["Keytruda", "Humira"]

        result = fetcher.fetch(
            feeds={"test_source": test_feed_url},
            days_back=30,
        )

        assert result["status"] == "success"
        assert result["record_count"] == 2
        assert result["hash"] is not None
        assert len(result["records"]) == 2

        # Verify first record
        rec = result["records"][0]
        assert "article_id" in rec
        assert rec["source_name"] == "test_source"
        assert "Keytruda" in rec["title"]

    @responses.activate
    def test_fetch_empty_feed(self, tmp_path):
        """Test fetch with an empty RSS feed."""
        test_feed_url = "https://test.example.com/rss.xml"
        responses.add(
            responses.GET,
            test_feed_url,
            body=SAMPLE_RSS_EMPTY.encode(),
            status=200,
            content_type="application/rss+xml",
        )

        fetcher = MedicalNewsFetcher(data_dir=str(tmp_path))
        fetcher._drug_names = []

        result = fetcher.fetch(
            feeds={"test_source": test_feed_url},
            days_back=30,
        )

        assert result["status"] == "success"
        assert result["record_count"] == 0

    @responses.activate
    def test_fetch_http_error(self, tmp_path):
        """Test fetch handles HTTP errors per feed gracefully."""
        test_feed_url = "https://test.example.com/rss.xml"
        responses.add(
            responses.GET,
            test_feed_url,
            body=b"Internal Server Error",
            status=500,
        )

        fetcher = MedicalNewsFetcher(data_dir=str(tmp_path))
        fetcher._drug_names = []

        result = fetcher.fetch(
            feeds={"test_source": test_feed_url},
            days_back=30,
        )

        # Per-feed errors are caught, overall succeeds with 0 records
        assert result["status"] == "success"
        assert result["record_count"] == 0

    @responses.activate
    def test_fetch_multiple_feeds(self, tmp_path):
        """Test fetch from multiple RSS feeds."""
        url1 = "https://feed1.example.com/rss.xml"
        url2 = "https://feed2.example.com/rss.xml"

        responses.add(
            responses.GET, url1,
            body=SAMPLE_RSS_XML.encode(), status=200,
            content_type="application/rss+xml",
        )
        responses.add(
            responses.GET, url2,
            body=SAMPLE_RSS_EMPTY.encode(), status=200,
            content_type="application/rss+xml",
        )

        fetcher = MedicalNewsFetcher(data_dir=str(tmp_path))
        fetcher._drug_names = []

        result = fetcher.fetch(
            feeds={"source1": url1, "source2": url2},
            days_back=30,
        )

        assert result["status"] == "success"
        assert result["record_count"] == 2


# ---------------------------------------------------------------------------
# Fetcher tests: drug mention extraction
# ---------------------------------------------------------------------------

class TestDrugMentionExtraction:
    """Tests for drug mention extraction from text."""

    def test_extract_drug_mentions_found(self):
        """Drug names are detected in text."""
        text = "New trial shows Keytruda and Humira efficacy in patients."
        drug_names = ["Keytruda", "Humira", "Opdivo"]
        mentions = MedicalNewsFetcher._extract_drug_mentions(text, drug_names)
        assert "Keytruda" in mentions
        assert "Humira" in mentions
        assert "Opdivo" not in mentions

    def test_extract_drug_mentions_case_insensitive(self):
        """Drug detection is case-insensitive."""
        text = "keytruda is a new drug"
        mentions = MedicalNewsFetcher._extract_drug_mentions(text, ["Keytruda"])
        assert "Keytruda" in mentions

    def test_extract_drug_mentions_none(self):
        """No drug mentions when text is empty."""
        mentions = MedicalNewsFetcher._extract_drug_mentions("", ["Keytruda"])
        assert mentions == []

    def test_extract_drug_mentions_no_drugs(self):
        """No drug mentions when drug list is empty."""
        mentions = MedicalNewsFetcher._extract_drug_mentions("some text", [])
        assert mentions == []


# ---------------------------------------------------------------------------
# Fetcher tests: article ID generation
# ---------------------------------------------------------------------------

class TestArticleIDGeneration:
    """Tests for unique article ID generation."""

    def test_generate_article_id_deterministic(self):
        """Same input produces the same article ID."""
        id1 = MedicalNewsFetcher._generate_article_id("source", "https://example.com/1")
        id2 = MedicalNewsFetcher._generate_article_id("source", "https://example.com/1")
        assert id1 == id2

    def test_generate_article_id_unique(self):
        """Different inputs produce different article IDs."""
        id1 = MedicalNewsFetcher._generate_article_id("source", "https://example.com/1")
        id2 = MedicalNewsFetcher._generate_article_id("source", "https://example.com/2")
        assert id1 != id2

    def test_generate_article_id_length(self):
        """Article ID is 32 characters (hex digest)."""
        article_id = MedicalNewsFetcher._generate_article_id("src", "url")
        assert len(article_id) == 32


# ---------------------------------------------------------------------------
# Fetcher tests: HTML cleaning
# ---------------------------------------------------------------------------

class TestHTMLCleaning:
    """Tests for HTML tag removal."""

    def test_clean_html_removes_tags(self):
        """HTML tags are stripped from text."""
        html = "<p>This is <b>bold</b> text.</p>"
        result = MedicalNewsFetcher._clean_html(html)
        assert result == "This is bold text."

    def test_clean_html_normalizes_whitespace(self):
        """Extra whitespace is collapsed."""
        html = "<p>Multiple   spaces   here</p>"
        result = MedicalNewsFetcher._clean_html(html)
        assert result == "Multiple spaces here"

    def test_clean_html_empty(self):
        """Empty string returns empty."""
        assert MedicalNewsFetcher._clean_html("") == ""


# ---------------------------------------------------------------------------
# Validator tests: valid records
# ---------------------------------------------------------------------------

class TestMedicalNewsRecordValid:
    """Tests for valid MedicalNewsRecord instances."""

    def test_full_record(self):
        """Fully populated record validates successfully."""
        record = MedicalNewsRecord(
            article_id="abc123def456",
            source_name="medscape",
            title="New Drug Shows Promise",
            summary="A new drug has been approved.",
            publication_date=date(2026, 2, 10),
            url="https://www.medscape.com/article/12345",
            drug_mentions=["Keytruda", "Humira"],
            therapeutic_areas=["Oncology"],
        )
        assert record.article_id == "abc123def456"
        assert record.source_name == "medscape"
        assert record.drug_mentions == ["Keytruda", "Humira"]

    def test_minimal_record(self):
        """Minimal record with only required fields."""
        record = MedicalNewsRecord(
            article_id="min123",
            source_name="healio",
        )
        assert record.article_id == "min123"
        assert record.source_name == "healio"
        assert record.title is None
        assert record.drug_mentions is None


# ---------------------------------------------------------------------------
# Validator tests: invalid records
# ---------------------------------------------------------------------------

class TestMedicalNewsRecordInvalid:
    """Tests for invalid MedicalNewsRecord instances."""

    def test_empty_article_id(self):
        """Empty article_id is rejected."""
        with pytest.raises(Exception):
            MedicalNewsRecord(article_id="", source_name="test")

    def test_missing_article_id(self):
        """Missing article_id is rejected."""
        with pytest.raises(Exception):
            MedicalNewsRecord(source_name="test")

    def test_empty_source_name(self):
        """Empty source_name is rejected."""
        with pytest.raises(Exception):
            MedicalNewsRecord(article_id="test123", source_name="")

    def test_missing_source_name(self):
        """Missing source_name is rejected."""
        with pytest.raises(Exception):
            MedicalNewsRecord(article_id="test123")
