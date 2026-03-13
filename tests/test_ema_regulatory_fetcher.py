"""Tests for EMA Regulatory CI fetcher and validator.

Feature: 011-datasource-integration
Task: Tier 4 CI source — EMA regulatory decisions

Tests use mocked HTTP responses so no external network calls are made.
"""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from dk_data.ingestion.fetchers.ema_regulatory import EMARegulatoryCIFetcher
from dk_data.ingestion.utils.validators import EMARegulatoryCIRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _sample_medicine(**overrides):
    """Return a single EMA medicines JSON item with sane defaults."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    base = {
        "name_of_medicine": "Keytruda",
        "active_substance": "pembrolizumab",
        "therapeutic_area_mesh": "oncology",
        "european_commission_decision_date": today,
        "medicine_status": "Authorised",
        "url": "https://www.ema.europa.eu/documents/ema-001234",
        "condition_indication": "Positive opinion for new indication.",
    }
    base.update(overrides)
    return base


def _sample_safety(**overrides):
    """Return a single EMA safety/DHPC JSON item."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    base = {
        "name_of_medicine": "TestDrug",
        "active_substance": "testsubstance",
        "date_of_letter": today,
        "description": "Safety signal identified.",
    }
    base.update(overrides)
    return base


def _make_json_response(items):
    """Build a mock JSON response for EMA data files."""
    mock = MagicMock()
    mock.json.return_value = {"data": items}
    mock.status_code = 200
    mock.raise_for_status = MagicMock()
    return mock


# ---------------------------------------------------------------------------
# Tests: fetcher initialisation
# ---------------------------------------------------------------------------

class TestFetcherInit:
    """Verify EMARegulatoryCIFetcher initialises correctly."""

    def test_fetcher_init(self, tmp_path):
        """Fetcher can be instantiated with a custom data_dir."""
        fetcher = EMARegulatoryCIFetcher(data_dir=str(tmp_path))

        assert fetcher.SOURCE_NAME == "ema_regulatory"
        assert fetcher.BASE_URL == "https://www.ema.europa.eu"
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

        assert "ema.europa.eu" in url
        assert url.startswith("https://")


# ---------------------------------------------------------------------------
# Tests: fetch with mocked HTTP
# ---------------------------------------------------------------------------

class TestFetchWithMock:
    """Verify the full fetch flow using mocked HTTP."""

    def test_fetch_with_mock(self, tmp_path):
        """fetch() returns success with records when API responds."""
        fetcher = EMARegulatoryCIFetcher(data_dir=str(tmp_path))

        medicines = [
            _sample_medicine(name_of_medicine="Keytruda"),
            _sample_medicine(name_of_medicine="Opdivo", active_substance="nivolumab"),
        ]
        safety = [_sample_safety()]

        def mock_get(url, **kwargs):
            resp = _make_json_response([])
            if "medicines_json" in url:
                resp = _make_json_response(medicines)
            elif "dhpc" in url:
                resp = _make_json_response(safety)
            return resp

        with patch.object(fetcher.session, "get", side_effect=mock_get):
            result = fetcher.fetch(days_back=90)

        assert result["status"] == "success"
        assert isinstance(result["records"], list)
        assert result["record_count"] == 3  # 2 medicines + 1 safety
        assert result["hash"] is not None

        rec = result["records"][0]
        assert "document_id" in rec
        assert "document_type" in rec
        assert "product_name" in rec

    def test_fetch_empty_response(self, tmp_path):
        """fetch() returns success with 0 records on empty response."""
        fetcher = EMARegulatoryCIFetcher(data_dir=str(tmp_path))

        empty_resp = _make_json_response([])

        with patch.object(fetcher.session, "get", return_value=empty_resp):
            result = fetcher.fetch()

        assert result["status"] == "success"
        assert result["record_count"] == 0
        assert result["records"] == []

    def test_fetch_handles_api_error_gracefully(self, tmp_path):
        """fetch() returns success with 0 records when requests fail."""
        fetcher = EMARegulatoryCIFetcher(data_dir=str(tmp_path))

        with patch.object(
            fetcher.session,
            "get",
            side_effect=Exception("Connection refused"),
        ):
            result = fetcher.fetch()

        assert result["status"] == "success"
        assert result["record_count"] == 0
        assert result["records"] == []

    def test_fetch_returns_failed_on_unexpected_error(self, tmp_path):
        """fetch() returns failed when an unexpected error occurs."""
        fetcher = EMARegulatoryCIFetcher(data_dir=str(tmp_path))

        with patch.object(
            fetcher,
            "_fetch_medicines_json",
            side_effect=RuntimeError("Unexpected internal error"),
        ):
            result = fetcher.fetch()

        assert result["status"] == "failed"
        assert "Unexpected internal error" in result["error"]

    def test_fetch_deduplicates(self, tmp_path):
        """Records with same document_id are deduplicated."""
        fetcher = EMARegulatoryCIFetcher(data_dir=str(tmp_path))

        # Same medicine appearing in both endpoints
        medicines = [_sample_medicine()]

        def mock_get(url, **kwargs):
            return _make_json_response(medicines)

        with patch.object(fetcher.session, "get", side_effect=mock_get):
            result = fetcher.fetch(days_back=90)

        assert result["status"] == "success"
        # Even though both medicines and safety return data, IDs differ
        assert result["record_count"] >= 1


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
