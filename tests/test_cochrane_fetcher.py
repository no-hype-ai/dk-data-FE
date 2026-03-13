"""Tests for Cochrane Fetcher and CochraneReviewRecord validator.

Feature: 011-datasource-integration
Task: T064-T066 — Cochrane systematic reviews

Tests cover:
- Fetcher initialization and session configuration
- get_latest_url endpoint
- Full fetch with mocked PubMed API
- CochraneReviewRecord validation (valid and invalid)
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from dk_data.ingestion.fetchers.cochrane import CochraneFetcher
from dk_data.ingestion.utils.validators import CochraneReviewRecord


# ---------------------------------------------------------------------------
# Sample PubMed API response fixtures
# ---------------------------------------------------------------------------

SAMPLE_ESEARCH_RESPONSE = {
    "esearchresult": {
        "count": "2",
        "retmax": "50",
        "idlist": ["38000001", "38000002"],
    }
}

SAMPLE_ESEARCH_EMPTY = {
    "esearchresult": {
        "count": "0",
        "retmax": "50",
        "idlist": [],
    }
}

# Minimal PubMed XML for testing
SAMPLE_EFETCH_XML = b"""<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>38000001</PMID>
      <Article>
        <ArticleTitle>Systemic corticosteroids for the treatment of COVID-19</ArticleTitle>
        <Abstract>
          <AbstractText>A systematic review of corticosteroids.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author><LastName>Wagner</LastName><Initials>C</Initials></Author>
          <Author><LastName>Griesel</LastName><Initials>M</Initials></Author>
        </AuthorList>
        <Journal>
          <JournalIssue><PubDate><Year>2026</Year><Month>Jan</Month><Day>15</Day></PubDate></JournalIssue>
        </Journal>
      </Article>
      <MeshHeadingList>
        <MeshHeading><DescriptorName>COVID-19</DescriptorName></MeshHeading>
      </MeshHeadingList>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="doi">10.1002/14651858.CD013600.pub2</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>38000002</PMID>
      <Article>
        <ArticleTitle>A minimal review record</ArticleTitle>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""


def _make_esearch_mock(data):
    """Build a mock response for PubMed ESearch."""
    mock = MagicMock()
    mock.json.return_value = data
    mock.status_code = 200
    mock.raise_for_status = MagicMock()
    return mock


def _make_efetch_mock(xml_bytes):
    """Build a mock response for PubMed EFetch."""
    mock = MagicMock()
    mock.content = xml_bytes
    mock.status_code = 200
    mock.raise_for_status = MagicMock()
    return mock


# ---------------------------------------------------------------------------
# Fetcher tests: initialization
# ---------------------------------------------------------------------------

class TestCochraneFetcherInit:
    """Tests for Cochrane fetcher initialization."""

    def test_fetcher_init(self, tmp_path):
        """Verify fetcher initializes with correct source name."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))
        assert fetcher.SOURCE_NAME == "cochrane"
        assert fetcher.session is not None
        assert fetcher.data_dir == tmp_path

    def test_fetcher_session_accepts_json(self, tmp_path):
        """Verify the Accept header requests JSON/XML."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))
        assert "application/json" in fetcher.session.headers.get("Accept", "")


# ---------------------------------------------------------------------------
# Fetcher tests: get_latest_url
# ---------------------------------------------------------------------------

class TestCochraneFetcherURL:
    """Tests for get_latest_url."""

    def test_get_latest_url(self, tmp_path):
        """Verify get_latest_url returns the PubMed search API."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))
        url = fetcher.get_latest_url()
        assert "ncbi.nlm.nih.gov" in url


# ---------------------------------------------------------------------------
# Fetcher tests: fetch with mocked HTTP
# ---------------------------------------------------------------------------

class TestCochraneFetcherFetch:
    """Tests for the fetch method with mocked HTTP responses."""

    def test_fetch_success(self, tmp_path):
        """Test complete fetch with mocked PubMed API."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))

        esearch_mock = _make_esearch_mock(SAMPLE_ESEARCH_RESPONSE)
        efetch_mock = _make_efetch_mock(SAMPLE_EFETCH_XML)

        def mock_get(url, **kwargs):
            if "esearch" in url:
                return esearch_mock
            return efetch_mock

        with patch.object(fetcher.session, "get", side_effect=mock_get):
            result = fetcher.fetch(
                search_terms=["corticosteroids"],
                days_back=90,
            )

        assert result["status"] == "success"
        assert result["record_count"] == 2
        assert result["hash"] is not None
        assert len(result["records"]) == 2

        rec = result["records"][0]
        assert rec["review_id"] == "pmid-38000001"
        assert rec["title"] == "Systemic corticosteroids for the treatment of COVID-19"
        assert rec["doi"] == "10.1002/14651858.CD013600.pub2"

    def test_fetch_empty_results(self, tmp_path):
        """Test fetch when no reviews are returned."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))

        esearch_mock = _make_esearch_mock(SAMPLE_ESEARCH_EMPTY)

        with patch.object(fetcher.session, "get", return_value=esearch_mock):
            result = fetcher.fetch(search_terms=["nonexistent_drug_xyz"])

        assert result["status"] == "success"
        assert result["record_count"] == 0
        assert result["records"] == []

    def test_fetch_api_error(self, tmp_path):
        """Test fetch handles API errors gracefully."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))

        with patch.object(
            fetcher.session,
            "get",
            side_effect=Exception("Connection refused"),
        ):
            result = fetcher.fetch(search_terms=["test"])

        # Per-term search catches exceptions, so overall succeeds with 0 records
        assert result["status"] == "success"
        assert result["record_count"] == 0

    def test_fetch_returns_failed_on_unexpected_error(self, tmp_path):
        """Test fetch returns failed on unexpected errors outside search loop."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))

        with patch.object(
            fetcher,
            "_search_reviews",
            side_effect=RuntimeError("Unexpected internal error"),
        ):
            result = fetcher.fetch(search_terms=["test"])

        assert result["status"] == "failed"
        assert "Unexpected internal error" in result["error"]

    def test_fetch_deduplicates_records(self, tmp_path):
        """Test that duplicate review IDs are deduplicated."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))

        esearch_mock = _make_esearch_mock(SAMPLE_ESEARCH_RESPONSE)
        efetch_mock = _make_efetch_mock(SAMPLE_EFETCH_XML)

        def mock_get(url, **kwargs):
            if "esearch" in url:
                return esearch_mock
            return efetch_mock

        with patch.object(fetcher.session, "get", side_effect=mock_get):
            result = fetcher.fetch(
                search_terms=["corticosteroids", "dexamethasone"],
            )

        assert result["status"] == "success"
        # Should be deduplicated to 2 unique reviews (same IDs from both terms)
        assert result["record_count"] == 2


# ---------------------------------------------------------------------------
# Validator tests: valid records
# ---------------------------------------------------------------------------

class TestCochraneReviewRecordValid:
    """Tests for valid CochraneReviewRecord instances."""

    def test_full_record(self):
        """Fully populated record validates successfully."""
        record = CochraneReviewRecord(
            review_id="CD013600",
            title="Systemic corticosteroids for COVID-19",
            authors="Wagner C; Griesel M",
            abstract="A systematic review of corticosteroids.",
            publication_date=date(2026, 1, 15),
            review_type="Intervention",
            interventions=["corticosteroids", "dexamethasone"],
            conditions=["COVID-19"],
            conclusions="Moderate-certainty evidence of benefit.",
            doi="10.1002/14651858.CD013600",
        )
        assert record.review_id == "CD013600"
        assert record.interventions == ["corticosteroids", "dexamethasone"]

    def test_minimal_record(self):
        """Minimal record with only required fields."""
        record = CochraneReviewRecord(review_id="CD000001")
        assert record.review_id == "CD000001"
        assert record.title is None
        assert record.authors is None
        assert record.interventions is None


# ---------------------------------------------------------------------------
# Validator tests: invalid records
# ---------------------------------------------------------------------------

class TestCochraneReviewRecordInvalid:
    """Tests for invalid CochraneReviewRecord instances."""

    def test_empty_review_id(self):
        """Empty review_id is rejected."""
        with pytest.raises(Exception):
            CochraneReviewRecord(review_id="")

    def test_missing_review_id(self):
        """Missing review_id is rejected."""
        with pytest.raises(Exception):
            CochraneReviewRecord()

    def test_whitespace_only_review_id(self):
        """Whitespace-only review_id is rejected."""
        with pytest.raises(Exception):
            CochraneReviewRecord(review_id="   ")
