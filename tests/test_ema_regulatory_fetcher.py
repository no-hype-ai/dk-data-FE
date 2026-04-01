"""Tests for EMA Regulatory CI fetcher and validator.

Feature: 011-datasource-integration
Task: Tier 4 CI source — EMA regulatory decisions

Tests use mocked HTTP responses so no external network calls are made.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from dk_data.ingestion.fetchers.ema_regulatory import EMARegulatoryCIFetcher
from dk_data.ingestion.utils.validators import EMARegulatoryCIRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_api_response(items, page_size=50):
    """Build a mock EMA API JSON response."""
    return {"results": items, "total": len(items), "page_size": page_size}


def _sample_item(**overrides):
    """Return a single EMA API item dict with sane defaults."""
    base = {
        "id": "EMA-001234",
        "product_name": "Keytruda",
        "active_substance": "pembrolizumab",
        "therapeutic_area": "oncology",
        "decision_date": "2026-02-10",
        "decision_type": "authorisation",
        "url": "https://www.ema.europa.eu/documents/ema-001234",
        "summary": "Positive opinion for new indication.",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests: fetcher initialisation
# ---------------------------------------------------------------------------

class TestFetcherInit:
    """Verify EMARegulatoryCIFetcher initialises correctly."""

    def test_fetcher_init(self, tmp_path):
        """Fetcher can be instantiated with a custom data_dir."""
        fetcher = EMARegulatoryCIFetcher(data_dir=str(tmp_path))

        assert fetcher.SOURCE_NAME == "ema_regulatory"
        assert fetcher.BASE_URL == "https://www.ema.europa.eu/en/medicines"
        assert fetcher.data_dir == tmp_path
        assert fetcher.session is not None

    def test_fetcher_init_defaults(self):
        """Fetcher can be instantiated with default data_dir."""
        fetcher = EMARegulatoryCIFetcher()

        assert fetcher.SOURCE_NAME == "ema_regulatory"
        assert fetcher.data_dir.exists()


# ---------------------------------------------------------------------------
# Tests: get_latest_url
# ---------------------------------------------------------------------------

class TestGetLatestUrl:
    """Verify the URL returned by get_latest_url."""

    def test_get_latest_url(self, tmp_path):
        fetcher = EMARegulatoryCIFetcher(data_dir=str(tmp_path))
        url = fetcher.get_latest_url()

        assert url == "https://www.ema.europa.eu/en/documents/report/medicines-output-medicines_json-report_en.json"
        assert url.startswith("https://")


# ---------------------------------------------------------------------------
# Tests: fetch with mocked HTTP
# ---------------------------------------------------------------------------

class TestFetchWithMock:
    """Verify the full fetch flow using mocked HTTP."""

    def test_fetch_with_mock(self, tmp_path):
        """fetch() returns success with records when API responds."""
        fetcher = EMARegulatoryCIFetcher(data_dir=str(tmp_path))

        items = [
            _sample_item(id="EMA-001"),
            _sample_item(id="EMA-002", decision_type="variation"),
            _sample_item(id="EMA-003", decision_type="withdrawal"),
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = _make_api_response(items)
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.session, "get", return_value=mock_response):
            # days_back is accepted for API compatibility but ignored (bulk snapshot source)
            result = fetcher.fetch(days_back=7)

        assert result["status"] == "success"
        assert isinstance(result["records"], list)
        # Bulk download returns all 3 items (no date filter applied)
        assert result["record_count"] == 3
        assert result["hash"] is not None

        # Verify record structure
        rec = result["records"][0]
        assert "document_id" in rec
        assert "document_type" in rec
        assert "product_name" in rec

    def test_fetch_empty_response(self, tmp_path):
        """fetch() returns success with 0 records on empty API response."""
        fetcher = EMARegulatoryCIFetcher(data_dir=str(tmp_path))

        mock_response = MagicMock()
        mock_response.json.return_value = _make_api_response([])
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.session, "get", return_value=mock_response):
            result = fetcher.fetch()

        assert result["status"] == "success"
        assert result["record_count"] == 0
        assert result["records"] == []

    def test_fetch_handles_api_error_gracefully(self, tmp_path):
        """fetch() returns failed when the bulk download request fails."""
        fetcher = EMARegulatoryCIFetcher(data_dir=str(tmp_path))

        with patch.object(
            fetcher.session,
            "get",
            side_effect=Exception("Connection refused"),
        ):
            result = fetcher.fetch()

        assert result["status"] == "failed"
        assert result["records"] == []

    def test_fetch_returns_failed_on_unexpected_error(self, tmp_path):
        """fetch() returns failed when _fetch_bulk raises unexpectedly."""
        fetcher = EMARegulatoryCIFetcher(data_dir=str(tmp_path))

        with patch.object(
            fetcher,
            "_fetch_bulk",
            side_effect=RuntimeError("Unexpected internal error"),
        ):
            result = fetcher.fetch()

        assert result["status"] == "failed"
        assert "Unexpected internal error" in result["error"]

    def test_fetch_bulk_single_call(self, tmp_path):
        """fetch() makes a single HTTP request for the bulk JSON (no pagination)."""
        fetcher = EMARegulatoryCIFetcher(data_dir=str(tmp_path))

        items = [_sample_item(id=f"EMA-{i}") for i in range(10)]
        mock_response = MagicMock()
        mock_response.json.return_value = _make_api_response(items)
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        call_count = 0

        def mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_response

        with patch.object(fetcher.session, "get", side_effect=mock_get):
            result = fetcher.fetch()

        assert result["status"] == "success"
        assert call_count == 1  # Bulk source: exactly one HTTP request
        assert result["record_count"] == 10

    def test_fetch_deduplicates_by_document_id(self, tmp_path):
        """Records with duplicate document_ids in the bulk response are deduplicated."""
        fetcher = EMARegulatoryCIFetcher(data_dir=str(tmp_path))

        # Two items with the same id
        items = [_sample_item(id="EMA-DUPE-001"), _sample_item(id="EMA-DUPE-001")]

        mock_response = MagicMock()
        mock_response.json.return_value = _make_api_response(items)
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.session, "get", return_value=mock_response):
            result = fetcher.fetch()

        assert result["record_count"] == 1


# ---------------------------------------------------------------------------
# Tests: Pydantic validator — valid records
# ---------------------------------------------------------------------------

class TestEMARegulatoryCIRecordValid:
    """Test that valid records pass Pydantic validation."""

    def test_ema_regulatory_record_valid(self):
        """A fully populated record validates successfully."""
        record = EMARegulatoryCIRecord(
            document_id="EMA-001234",
            document_type="chmp_opinion",
            product_name="Keytruda",
            active_substance="pembrolizumab",
            therapeutic_area="oncology",
            decision_date="2026-02-10",
            decision_type="authorisation",
            document_url="https://www.ema.europa.eu/documents/ema-001234",
            summary="Positive CHMP opinion for new indication.",
        )

        assert record.document_id == "EMA-001234"
        assert record.document_type == "chmp_opinion"
        assert record.decision_date == date(2026, 2, 10)
        assert record.decision_type == "authorisation"

    def test_minimal_record(self):
        """A record with only document_id validates."""
        record = EMARegulatoryCIRecord(document_id="EMA-MINIMAL")
        assert record.document_id == "EMA-MINIMAL"
        assert record.decision_type is None
        assert record.decision_date is None

    def test_decision_date_as_date_object(self):
        """decision_date accepts a Python date object."""
        record = EMARegulatoryCIRecord(
            document_id="EMA-D001",
            decision_date=date(2026, 1, 15),
        )
        assert record.decision_date == date(2026, 1, 15)

    def test_all_valid_decision_types(self):
        """Every entry in VALID_DECISION_TYPES is accepted."""
        for dt in EMARegulatoryCIRecord.VALID_DECISION_TYPES:
            record = EMARegulatoryCIRecord(
                document_id=f"EMA-{dt}",
                decision_type=dt,
            )
            assert record.decision_type == dt


# ---------------------------------------------------------------------------
# Tests: Pydantic validator — invalid records
# ---------------------------------------------------------------------------

class TestEMARegulatoryCIRecordInvalid:
    """Test that invalid records are rejected by Pydantic."""

    def test_ema_regulatory_record_invalid_decision_type(self):
        """An unrecognised decision_type raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            EMARegulatoryCIRecord(
                document_id="EMA-BAD-DT",
                decision_type="magic_approval",
            )

        errors = exc_info.value.errors()
        assert any("decision_type" in str(e) for e in errors)

    def test_empty_document_id_rejected(self):
        """An empty document_id string is rejected."""
        with pytest.raises(ValidationError):
            EMARegulatoryCIRecord(document_id="")

    def test_missing_document_id_rejected(self):
        """Omitting document_id entirely raises ValidationError."""
        with pytest.raises(ValidationError):
            EMARegulatoryCIRecord()

    def test_invalid_date_string(self):
        """A malformed date string raises ValidationError."""
        with pytest.raises(ValidationError):
            EMARegulatoryCIRecord(
                document_id="EMA-BAD-DATE",
                decision_date="not-a-date",
            )

    def test_document_id_too_long(self):
        """A document_id exceeding max_length is rejected."""
        with pytest.raises(ValidationError):
            EMARegulatoryCIRecord(document_id="X" * 101)
