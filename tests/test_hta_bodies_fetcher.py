"""Tests for HTA Bodies fetcher and validator with mocked HTTP.

Feature: 011-datasource-integration
Task: T058-T060 — HTA Bodies CI source integration

Tests use mocked HTTP responses so no external network calls are made.
"""

import tempfile
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from dk_data.ingestion.fetchers.hta_bodies import (
    AGENCIES,
    NICE_API_BASE,
    HTABodiesFetcher,
)
from dk_data.ingestion.utils.validators import HTADecisionRecord


# ---------------------------------------------------------------------------
# Sample NICE API response fixtures
# ---------------------------------------------------------------------------

def _make_nice_response(items):
    """Build a mock NICE API JSON response."""
    return {"results": items, "total": len(items)}


def _sample_nice_item(**overrides):
    """Return a single NICE guidance item dict with sane defaults."""
    base = {
        "id": "TA900",
        "title": "Pembrolizumab for advanced melanoma",
        "drug_name": "Pembrolizumab",
        "indication": "Advanced melanoma",
        "decision_type": "Recommended",
        "published_date": "2026-02-05",
        "url": "https://www.nice.org.uk/guidance/ta900",
        "summary": "Pembrolizumab is recommended for treating advanced melanoma.",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Fetcher initialisation tests
# ---------------------------------------------------------------------------

class TestHTABodiesFetcherInit:
    """Tests for fetcher initialization."""

    def test_fetcher_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = HTABodiesFetcher(data_dir=tmpdir)
            assert fetcher.SOURCE_NAME == "hta_bodies"
            assert fetcher.session is not None

    def test_fetcher_init_defaults(self):
        fetcher = HTABodiesFetcher()
        assert fetcher.SOURCE_NAME == "hta_bodies"
        assert fetcher.data_dir.exists()

    def test_get_latest_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = HTABodiesFetcher(data_dir=tmpdir)
            url = fetcher.get_latest_url()
            assert url == NICE_API_BASE
            assert "nice.org.uk" in url


# ---------------------------------------------------------------------------
# Fetch with mocked HTTP
# ---------------------------------------------------------------------------

class TestHTABodiesFetch:
    """Tests for the fetch method with mocked HTTP responses."""

    def test_fetch_nice_success(self, tmp_path):
        """NICE API returns guidance items."""
        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        items = [
            _sample_nice_item(id="TA900"),
            _sample_nice_item(
                id="TA901",
                drug_name="Nivolumab",
                title="Nivolumab for lung cancer",
            ),
        ]

        mock_response = MagicMock()
        mock_response.json.return_value = _make_nice_response(items)
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.session, "get", return_value=mock_response):
            result = fetcher.fetch(
                drug_names=["pembrolizumab", "nivolumab"],
                agencies=["nice"],
                days_back=30,
            )

        assert result["status"] == "success"
        assert len(result["records"]) == 2
        assert result["hash"] is not None

        rec = result["records"][0]
        assert rec["decision_id"] == "nice-TA900"
        assert rec["agency"] == "nice"
        assert rec["drug_name"] == "Pembrolizumab"

    def test_fetch_nice_empty_response(self, tmp_path):
        """NICE API returns no items."""
        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        mock_response = MagicMock()
        mock_response.json.return_value = _make_nice_response([])
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.session, "get", return_value=mock_response):
            result = fetcher.fetch(
                drug_names=["nonexistent_drug"],
                agencies=["nice"],
            )

        assert result["status"] == "success"
        assert result["records"] == []

    def test_fetch_nice_api_error_handled(self, tmp_path):
        """NICE API error is handled gracefully."""
        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        with patch.object(
            fetcher.session,
            "get",
            side_effect=Exception("Connection refused"),
        ):
            result = fetcher.fetch(
                drug_names=["pembrolizumab"],
                agencies=["nice"],
            )

        assert result["status"] == "success"
        assert result["records"] == []

    def test_fetch_stub_agencies_return_empty(self, tmp_path):
        """Stub agencies (gba, has, pbac) return empty results."""
        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        result = fetcher.fetch(
            drug_names=["pembrolizumab"],
            agencies=["gba", "has", "pbac"],
        )

        assert result["status"] == "success"
        assert result["records"] == []

    def test_fetch_all_agencies(self, tmp_path):
        """Fetch across all agencies (NICE + stubs)."""
        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        items = [_sample_nice_item(id="TA900")]
        mock_response = MagicMock()
        mock_response.json.return_value = _make_nice_response(items)
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.session, "get", return_value=mock_response):
            result = fetcher.fetch(
                drug_names=["pembrolizumab"],
                agencies=AGENCIES,
            )

        assert result["status"] == "success"
        # Only NICE returns data; stubs return empty
        assert len(result["records"]) == 1
        assert result["records"][0]["agency"] == "nice"

    def test_fetch_drug_name_filtering(self, tmp_path):
        """Drug name filtering correctly includes/excludes items."""
        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        items = [
            _sample_nice_item(
                id="TA900",
                drug_name="Pembrolizumab",
                summary="For melanoma treatment",
            ),
            _sample_nice_item(
                id="TA901",
                drug_name="Aspirin",
                summary="For pain relief",
            ),
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = _make_nice_response(items)
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.session, "get", return_value=mock_response):
            result = fetcher.fetch(
                drug_names=["pembrolizumab"],
                agencies=["nice"],
            )

        assert result["status"] == "success"
        # Only pembrolizumab should match
        assert len(result["records"]) == 1
        assert result["records"][0]["drug_name"] == "Pembrolizumab"

    def test_fetch_no_drug_names_returns_all(self, tmp_path):
        """When no drug_names are specified, all items are returned."""
        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        items = [
            _sample_nice_item(id="TA900"),
            _sample_nice_item(id="TA901", drug_name="Aspirin"),
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = _make_nice_response(items)
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.session, "get", return_value=mock_response):
            result = fetcher.fetch(
                drug_names=[],
                agencies=["nice"],
            )

        assert result["status"] == "success"
        assert len(result["records"]) == 2

    def test_fetch_deduplication_across_agencies(self, tmp_path):
        """Decisions with the same ID are deduplicated."""
        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        items = [_sample_nice_item(id="TA900")]
        mock_response = MagicMock()
        mock_response.json.return_value = _make_nice_response(items)
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        # Call nice twice to simulate overlap
        with patch.object(fetcher.session, "get", return_value=mock_response):
            with patch.object(
                fetcher,
                "_fetch_agency",
                side_effect=[
                    [{"decision_id": "nice-TA900", "agency": "nice", "drug_name": "Test"}],
                    [{"decision_id": "nice-TA900", "agency": "nice", "drug_name": "Test"}],
                ],
            ):
                result = fetcher.fetch(
                    drug_names=["test"],
                    agencies=["nice", "nice"],
                )

        assert result["status"] == "success"
        assert len(result["records"]) == 1


# ---------------------------------------------------------------------------
# NICE item normalisation tests
# ---------------------------------------------------------------------------

class TestNICENormalization:
    """Tests for NICE item normalization."""

    def test_normalize_full_item(self):
        item = _sample_nice_item()
        record = HTABodiesFetcher._normalize_nice_item(item)
        assert record is not None
        assert record["decision_id"] == "nice-TA900"
        assert record["agency"] == "nice"
        assert record["drug_name"] == "Pembrolizumab"
        assert record["decision_date"] == "2026-02-05"
        assert record["document_url"] == "https://www.nice.org.uk/guidance/ta900"

    def test_normalize_missing_id(self):
        item = {"title": "No ID item", "drug_name": "Test"}
        record = HTABodiesFetcher._normalize_nice_item(item)
        assert record is None

    def test_normalize_with_guidance_id(self):
        item = _sample_nice_item()
        del item["id"]
        item["guidance_id"] = "TA999"
        record = HTABodiesFetcher._normalize_nice_item(item)
        assert record["decision_id"] == "nice-TA999"

    def test_extract_items_from_list(self):
        items = [{"id": "1"}, {"id": "2"}]
        result = HTABodiesFetcher._extract_items(items)
        assert len(result) == 2

    def test_extract_items_from_dict(self):
        data = {"results": [{"id": "1"}]}
        result = HTABodiesFetcher._extract_items(data)
        assert len(result) == 1

    def test_extract_items_empty(self):
        result = HTABodiesFetcher._extract_items({})
        assert result == []


# ---------------------------------------------------------------------------
# HTADecisionRecord validator tests
# ---------------------------------------------------------------------------

class TestHTADecisionRecord:
    """Tests for the HTADecisionRecord Pydantic model."""

    def test_valid_record(self):
        record = HTADecisionRecord(
            decision_id="nice-TA900",
            agency="nice",
            drug_name="Pembrolizumab",
            indication="Advanced melanoma",
            decision_type="Recommended",
            decision_date=date(2026, 2, 5),
            document_url="https://www.nice.org.uk/guidance/ta900",
            summary="Recommended for treating advanced melanoma.",
        )
        assert record.decision_id == "nice-TA900"
        assert record.agency == "nice"
        assert record.drug_name == "Pembrolizumab"

    def test_minimal_record(self):
        record = HTADecisionRecord(
            decision_id="nice-TA001",
            agency="nice",
        )
        assert record.decision_id == "nice-TA001"
        assert record.drug_name is None
        assert record.indication is None

    def test_all_valid_agencies(self):
        for agency in HTADecisionRecord.VALID_AGENCIES:
            record = HTADecisionRecord(
                decision_id=f"{agency}-001",
                agency=agency,
            )
            assert record.agency == agency

    def test_invalid_agency_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            HTADecisionRecord(
                decision_id="fda-001",
                agency="fda",
            )
        assert "agency" in str(exc_info.value).lower()

    def test_empty_decision_id_rejected(self):
        with pytest.raises(ValidationError):
            HTADecisionRecord(decision_id="", agency="nice")

    def test_missing_decision_id_rejected(self):
        with pytest.raises(ValidationError):
            HTADecisionRecord(agency="nice")

    def test_empty_agency_rejected(self):
        with pytest.raises(ValidationError):
            HTADecisionRecord(decision_id="nice-001", agency="")

    def test_agency_case_insensitive(self):
        record = HTADecisionRecord(
            decision_id="nice-001",
            agency="NICE",
        )
        assert record.agency == "nice"

    def test_whitespace_stripped(self):
        record = HTADecisionRecord(
            decision_id="  nice-001  ",
            agency="  nice  ",
        )
        assert record.decision_id == "nice-001"
        assert record.agency == "nice"
