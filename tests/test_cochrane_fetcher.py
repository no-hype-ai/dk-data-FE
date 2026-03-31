"""Tests for Cochrane Fetcher and CochraneReviewRecord validator.

Feature: 011-datasource-integration
Task: T064-T066 — Cochrane systematic reviews

Tests cover:
- Fetcher initialization and session configuration
- get_latest_url endpoint
- Full fetch with mocked Cochrane API
- CochraneReviewRecord validation (valid and invalid)
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from dk_data.ingestion.fetchers.cochrane import CochraneFetcher
from dk_data.ingestion.utils.validators import CochraneReviewRecord


# ---------------------------------------------------------------------------
# Sample Cochrane API response fixtures
# ---------------------------------------------------------------------------

SAMPLE_REVIEW_ITEM = {
    "id": "CD013600",
    "title": "Systemic corticosteroids for the treatment of COVID-19",
    "authors": ["Wagner C", "Griesel M", "Mikolajewska A"],
    "abstract": "Systemic corticosteroids are used to treat COVID-19 as they reduce inflammation.",
    "publishDate": "2026-01-15",
    "reviewType": "Intervention",
    "interventions": ["corticosteroids", "dexamethasone"],
    "conditions": ["COVID-19"],
    "conclusions": "Moderate-certainty evidence that corticosteroids reduce mortality.",
    "doi": "10.1002/14651858.CD013600.pub2",
}

SAMPLE_REVIEW_MINIMAL = {
    "id": "CD012345",
    "title": "A minimal review record",
}


def _make_cochrane_response(items):
    """Build a mock Cochrane API response body."""
    return {
        "results": items,
        "resultCount": len(items),
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
# Fetcher tests: get_latest_url
# ---------------------------------------------------------------------------

class TestCochraneFetcherURL:
    """Tests for get_latest_url."""

    def test_get_latest_url(self, tmp_path):
        """Verify get_latest_url returns the Cochrane search API."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))
        url = fetcher.get_latest_url()
        assert "cochranelibrary.com" in url


# ---------------------------------------------------------------------------
# Fetcher tests: fetch with mocked HTTP
# ---------------------------------------------------------------------------

class TestCochraneFetcherFetch:
    """Tests for the fetch method with mocked HTTP responses."""

    def test_fetch_success(self, tmp_path):
        """Test complete fetch with mocked Cochrane API."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))

        items = [SAMPLE_REVIEW_ITEM, SAMPLE_REVIEW_MINIMAL]
        mock_response = MagicMock()
        mock_response.json.return_value = _make_cochrane_response(items)
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.session, "get", return_value=mock_response):
            result = fetcher.fetch(
                search_terms=["corticosteroids"],
                days_back=90,
            )

        assert result["status"] == "success"
        assert result["record_count"] == 2
        assert result["hash"] is not None
        assert len(result["records"]) == 2

        rec = result["records"][0]
        assert rec["review_id"] == "CD013600"
        assert rec["title"] == "Systemic corticosteroids for the treatment of COVID-19"
        assert rec["doi"] == "10.1002/14651858.CD013600.pub2"
        assert rec["interventions"] == ["corticosteroids", "dexamethasone"]
        assert rec["conditions"] == ["COVID-19"]

    def test_fetch_empty_results(self, tmp_path):
        """Test fetch when no reviews are returned."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))

        mock_response = MagicMock()
        mock_response.json.return_value = _make_cochrane_response([])
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.session, "get", return_value=mock_response):
            result = fetcher.fetch(search_terms=["nonexistent_drug_xyz"])

        assert result["status"] == "success"
        assert result["record_count"] == 0
        assert result["records"] == []

    def test_fetch_api_error(self, tmp_path):
        """Test fetch returns failed when the API is unreachable (network error)."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))

        with patch.object(
            fetcher.session,
            "get",
            side_effect=Exception("Connection refused"),
        ):
            result = fetcher.fetch(search_terms=["test"])

        # Pre-flight probe raises → outer exception handler → status=failed
        assert result["status"] == "failed"
        assert result["records"] == []

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

        # Same review ID from two different terms
        items = [SAMPLE_REVIEW_ITEM]
        mock_response = MagicMock()
        mock_response.json.return_value = _make_cochrane_response(items)
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.session, "get", return_value=mock_response):
            result = fetcher.fetch(
                search_terms=["corticosteroids", "dexamethasone"],
            )

        assert result["status"] == "success"
        # Should be deduplicated to 1 unique review
        assert result["record_count"] == 1


# ---------------------------------------------------------------------------
# Fetcher tests: normalization
# ---------------------------------------------------------------------------

class TestCochraneNormalization:
    """Tests for review record normalization."""

    def test_normalize_review_full(self, tmp_path):
        """Test normalization of a fully populated review."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))
        result = fetcher._normalize_review(SAMPLE_REVIEW_ITEM, "test")

        assert result["review_id"] == "CD013600"
        assert result["title"] == "Systemic corticosteroids for the treatment of COVID-19"
        assert result["authors"] == "Wagner C; Griesel M; Mikolajewska A"
        assert result["publication_date"] == "2026-01-15"
        assert result["interventions"] == ["corticosteroids", "dexamethasone"]

    def test_normalize_review_minimal(self, tmp_path):
        """Test normalization of a minimal review."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))
        result = fetcher._normalize_review(SAMPLE_REVIEW_MINIMAL, "test")

        assert result["review_id"] == "CD012345"
        assert result["title"] == "A minimal review record"
        assert result["authors"] is None
        assert result["interventions"] is None

    def test_normalize_review_no_id(self, tmp_path):
        """Test normalization returns None when no ID is available."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))
        result = fetcher._normalize_review({"title": "No ID"}, "test")
        assert result is None


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
