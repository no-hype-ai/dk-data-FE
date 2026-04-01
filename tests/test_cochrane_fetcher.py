"""Tests for Cochrane Fetcher (PubMed eUtils implementation).

Feature: 011-datasource-integration
Task: T064-T066 — Cochrane systematic reviews

The Cochrane Library's own API (cochranelibrary.com/api/search) is no longer
accessible (Cloudflare 404/419). The fetcher was migrated to use PubMed eUtils
(esearch + esummary) scoped to the Cochrane Database of Systematic Reviews.
See issue #189 for context.

Tests cover:
- Fetcher initialization and session configuration
- get_latest_url now returns PubMed eSearch URL
- fetch() with mocked PubMed responses
- _normalize_summary normalization
- CochraneReviewRecord validation (valid and invalid)
"""

from datetime import date
from unittest.mock import patch

import pytest

from dk_data.ingestion.fetchers.cochrane import (
    ESEARCH_URL,
    CochraneFetcher,
)
from dk_data.ingestion.utils.validators import CochraneReviewRecord


# ---------------------------------------------------------------------------
# Sample PubMed eSummary response fixtures
# ---------------------------------------------------------------------------

SAMPLE_ESEARCH_RESPONSE = {
    "esearchresult": {
        "idlist": ["38001234", "38005678"],
        "count": "2",
    }
}

SAMPLE_ESUMMARY_RESPONSE = {
    "result": {
        "38001234": {
            "uid": "38001234",
            "title": "Systemic corticosteroids for the treatment of COVID-19",
            "authors": [
                {"name": "Wagner C", "authtype": "Author"},
                {"name": "Griesel M", "authtype": "Author"},
                {"name": "Mikolajewska A", "authtype": "Author"},
            ],
            "pubdate": "2026 Jan 15",
            "articleids": [
                {"idtype": "doi", "value": "10.1002/14651858.CD013600.pub2"},
                {"idtype": "pubmed", "value": "38001234"},
            ],
            "source": "Cochrane Database Syst Rev",
        },
        "38005678": {
            "uid": "38005678",
            "title": "A minimal review record",
            "authors": [],
            "pubdate": "2026 Feb 01",
            "articleids": [],
            "source": "Cochrane Database Syst Rev",
        },
    }
}


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
        """Verify the Accept header requests JSON."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))
        assert fetcher.session.headers.get("Accept") == "application/json"


# ---------------------------------------------------------------------------
# Fetcher tests: get_latest_url (now returns PubMed eSearch URL)
# ---------------------------------------------------------------------------

class TestCochraneFetcherURL:
    """Tests for get_latest_url."""

    def test_get_latest_url_is_pubmed(self, tmp_path):
        """Verify get_latest_url returns the PubMed eSearch URL (not Cochrane)."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))
        url = fetcher.get_latest_url()
        assert "ncbi.nlm.nih.gov" in url
        assert "esearch" in url
        assert url == ESEARCH_URL

    def test_get_latest_url_not_cochrane_direct(self, tmp_path):
        """Verify the defunct Cochrane direct API is no longer used."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))
        url = fetcher.get_latest_url()
        assert "cochranelibrary.com" not in url


# ---------------------------------------------------------------------------
# Fetcher tests: fetch with mocked PubMed HTTP
# ---------------------------------------------------------------------------

class TestCochraneFetcherFetch:
    """Tests for the fetch method with mocked PubMed responses."""

    def _mock_fetch_json(self, url, params=None):
        """Return appropriate mock based on URL."""
        if "esearch" in url:
            return SAMPLE_ESEARCH_RESPONSE
        if "esummary" in url:
            return SAMPLE_ESUMMARY_RESPONSE
        return {}

    def test_fetch_success(self, tmp_path):
        """Test complete fetch with mocked PubMed API."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))

        with patch.object(fetcher, "fetch_json", side_effect=self._mock_fetch_json):
            result = fetcher.fetch(
                search_terms=["corticosteroids"],
                days_back=90,
            )

        assert result["status"] == "success"
        assert result["record_count"] == 2
        assert result["hash"] is not None
        assert len(result["records"]) == 2

        rec = result["records"][0]
        assert rec["review_id"] == "10.1002/14651858.CD013600.pub2"  # DOI used as ID
        assert rec["title"] == "Systemic corticosteroids for the treatment of COVID-19"
        assert rec["doi"] == "10.1002/14651858.CD013600.pub2"
        assert rec["pmid"] == "38001234"

    def test_fetch_empty_results(self, tmp_path):
        """Test fetch when no reviews are returned."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))

        def _empty_search(url, params=None):
            if "esearch" in url:
                return {"esearchresult": {"idlist": [], "count": "0"}}
            return {}

        with patch.object(fetcher, "fetch_json", side_effect=_empty_search):
            result = fetcher.fetch(search_terms=["nonexistent_drug_xyz"])

        assert result["status"] == "success"
        assert result["record_count"] == 0
        assert result["records"] == []

    def test_fetch_api_error(self, tmp_path):
        """Test fetch handles PubMed API errors gracefully."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))

        with patch.object(
            fetcher,
            "fetch_json",
            side_effect=Exception("Connection refused"),
        ):
            result = fetcher.fetch(search_terms=["test"])

        # Per-term search catches exceptions; overall succeeds with 0 records
        assert result["status"] == "success"
        assert result["record_count"] == 0

    def test_fetch_returns_failed_on_unexpected_error(self, tmp_path):
        """Test fetch returns failed on unexpected errors outside search loop."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))

        with patch.object(
            fetcher,
            "_search_pmids",
            side_effect=RuntimeError("Unexpected internal error"),
        ):
            result = fetcher.fetch(search_terms=["test"])

        assert result["status"] == "failed"
        assert "Unexpected internal error" in result["error"]

    def test_fetch_deduplicates_records(self, tmp_path):
        """Test that duplicate PMIDs are deduplicated across search terms."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))

        # Both terms return the same PMID
        def _same_pmid(url, params=None):
            if "esearch" in url:
                return {"esearchresult": {"idlist": ["38001234"], "count": "1"}}
            if "esummary" in url:
                return {
                    "result": {
                        "38001234": SAMPLE_ESUMMARY_RESPONSE["result"]["38001234"]
                    }
                }
            return {}

        with patch.object(fetcher, "fetch_json", side_effect=_same_pmid):
            result = fetcher.fetch(
                search_terms=["corticosteroids", "dexamethasone"],
            )

        assert result["status"] == "success"
        # Deduplicated to 1 unique review
        assert result["record_count"] == 1


# ---------------------------------------------------------------------------
# Fetcher tests: normalization (_normalize_summary)
# ---------------------------------------------------------------------------

class TestCochraneNormalization:
    """Tests for PubMed eSummary record normalization."""

    def test_normalize_summary_full(self, tmp_path):
        """Test normalization of a fully populated eSummary record."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))
        item = SAMPLE_ESUMMARY_RESPONSE["result"]["38001234"]
        result = fetcher._normalize_summary(item, "corticosteroids")

        assert result["review_id"] == "10.1002/14651858.CD013600.pub2"  # DOI preferred
        assert result["title"] == "Systemic corticosteroids for the treatment of COVID-19"
        assert result["authors"] == "Wagner C; Griesel M; Mikolajewska A"
        assert result["pmid"] == "38001234"
        assert result["doi"] == "10.1002/14651858.CD013600.pub2"
        assert result["publication_date"] == "2026 Jan 1"  # first 10 chars of "2026 Jan 15"

    def test_normalize_summary_no_doi(self, tmp_path):
        """Test normalization falls back to pmid: prefix when no DOI."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))
        item = {
            "uid": "38005678",
            "title": "A review without DOI",
            "authors": [],
            "pubdate": "2026 Feb",
            "articleids": [],
        }
        result = fetcher._normalize_summary(item, "test")

        assert result["review_id"] == "pmid:38005678"
        assert result["doi"] is None

    def test_normalize_summary_no_uid(self, tmp_path):
        """Test normalization returns None when no UID."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))
        result = fetcher._normalize_summary({"title": "No UID"}, "test")
        assert result is None

    # Legacy method name compatibility — _normalize_review was used in old tests
    def test_normalize_review_no_id(self, tmp_path):
        """Confirm _normalize_summary returns None when no UID (replaces old _normalize_review)."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))
        result = fetcher._normalize_summary({"title": "No ID"}, "test")
        assert result is None


# ---------------------------------------------------------------------------
# Validator tests: valid records (unchanged — CochraneReviewRecord still valid)
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
