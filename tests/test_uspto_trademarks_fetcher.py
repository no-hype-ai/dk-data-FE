"""Tests for USPTO Trademarks Fetcher and USPTOTrademarkRecord validator.

Feature: 014-uspto-euipo-model-datasource
Task: T026 — USPTO TSDR trademark fetcher tests

Tests cover:
- Fetcher initialization (with/without API key)
- get_latest_url endpoint
- Fetch with mocked HTTP (success, empty, batch, auth error, API error)
- Serial number deduplication
- Trademark normalization (_normalize_trademark)
- USPTOTrademarkRecord Pydantic validation (valid and invalid)
"""

import os
import tempfile
from datetime import date
from unittest.mock import patch

import pytest
import responses
from pydantic import ValidationError

from dk_data.ingestion.fetchers.uspto_trademarks import (
    USPTOTrademarksFetcher,
    BATCH_SIZE,
)
from dk_data.ingestion.utils.validators import USPTOTrademarkRecord


# ---------------------------------------------------------------------------
# Sample TSDR API response fixtures
# ---------------------------------------------------------------------------

SAMPLE_TSDR_CASE = {
    "serialNumber": "90123456",
    "markElement": "PHARMATEST",
    "markType": "Word Mark",
    "statusStr": "Registered",
    "statusCode": 800,
    "statusDate": "2024-06-01",
    "filingDate": "2024-01-15",
    "usRegistrationNumber": "6789012",
    "registrationDate": "2024-06-01",
    "gsList": [
        {
            "internationalClasses": [5],
            "goodsAndServicesText": "Pharmaceutical preparations for treatment of cancer",
        }
    ],
    "parties": {
        "currentOwners": [
            {
                "name": "Pharma Corp Inc.",
                "entityType": "Corporation",
            }
        ]
    },
    "goodsAndServicesText": "Pharmaceutical preparations",
    "descriptionOfMark": "The mark consists of standard characters without claim to any particular font style.",
}

SAMPLE_TSDR_CASE_MINIMAL = {
    "serialNumber": "90999999",
    "statusStr": "Filed",
}


def _make_tsdr_batch_response(cases):
    """Build a mock TSDR batch response (list of cases)."""
    return cases


# ---------------------------------------------------------------------------
# Tests: fetcher initialization
# ---------------------------------------------------------------------------

class TestUSPTOTrademarksFetcherInit:
    """Verify USPTOTrademarksFetcher initializes correctly."""

    def test_fetcher_init_with_api_key(self, tmp_path):
        """Fetcher reads API key from environment."""
        with patch.dict(os.environ, {"USPTO_TSDR_API_KEY": "test-tsdr-key"}):
            fetcher = USPTOTrademarksFetcher(data_dir=str(tmp_path))

        assert fetcher.SOURCE_NAME == "uspto_trademarks"
        assert fetcher.BASE_URL == "https://tsdrapi.uspto.gov"
        assert fetcher.api_key == "test-tsdr-key"
        assert fetcher.session is not None
        assert fetcher.session.headers.get("USPTO-API-KEY") == "test-tsdr-key"

    def test_fetcher_init_without_api_key(self, tmp_path):
        """Fetcher initializes without API key (with warning)."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("USPTO_TSDR_API_KEY", None)
            fetcher = USPTOTrademarksFetcher(data_dir=str(tmp_path))

        assert fetcher.api_key is None

    def test_fetcher_data_dir_set(self, tmp_path):
        """Fetcher stores the data directory."""
        with patch.dict(os.environ, {"USPTO_TSDR_API_KEY": "key"}):
            fetcher = USPTOTrademarksFetcher(data_dir=str(tmp_path))
        assert fetcher.data_dir == tmp_path


# ---------------------------------------------------------------------------
# Tests: get_latest_url
# ---------------------------------------------------------------------------

class TestUSPTOTrademarksGetLatestUrl:
    """Verify get_latest_url returns the TSDR base URL."""

    def test_get_latest_url(self, tmp_path):
        with patch.dict(os.environ, {"USPTO_TSDR_API_KEY": "key"}):
            fetcher = USPTOTrademarksFetcher(data_dir=str(tmp_path))
        url = fetcher.get_latest_url()
        assert url == "https://tsdrapi.uspto.gov"


# ---------------------------------------------------------------------------
# Tests: fetch with mocked HTTP
# ---------------------------------------------------------------------------

class TestUSPTOTrademarksFetchWithMock:
    """Tests for the fetch method with mocked HTTP responses."""

    @responses.activate
    def test_fetch_success(self):
        """fetch() returns success with normalized records."""
        responses.add(
            responses.GET,
            "https://tsdrapi.uspto.gov/ts/cd/caseMultiStatus/sn",
            json=_make_tsdr_batch_response([SAMPLE_TSDR_CASE, SAMPLE_TSDR_CASE_MINIMAL]),
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"USPTO_TSDR_API_KEY": "test-key"}):
                fetcher = USPTOTrademarksFetcher(data_dir=tmpdir)
            result = fetcher.fetch(serial_numbers=["90123456", "90999999"])

        assert result["status"] == "success"
        assert result["record_count"] == 2
        assert len(result["records"]) == 2
        assert result["hash"] is not None

        rec = result["records"][0]
        assert rec["serial_number"] == "90123456"
        assert rec["mark_element"] == "PHARMATEST"
        assert rec["status"] == "Registered"
        assert rec["owner_name"] == "Pharma Corp Inc."
        assert rec["nice_classes"] == [5]

    @responses.activate
    def test_fetch_empty_no_serial_numbers(self):
        """fetch() returns empty when no serial numbers and DB lookup fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"USPTO_TSDR_API_KEY": "test-key"}):
                fetcher = USPTOTrademarksFetcher(data_dir=tmpdir)

            # Mock _load_serial_numbers_from_db to return empty
            with patch.object(fetcher, "_load_serial_numbers_from_db", return_value=[]):
                result = fetcher.fetch()

        assert result["status"] == "success"
        assert result["record_count"] == 0
        assert result["records"] == []

    @responses.activate
    def test_fetch_auth_error(self):
        """fetch() handles 401 authentication error."""
        responses.add(
            responses.GET,
            "https://tsdrapi.uspto.gov/ts/cd/caseMultiStatus/sn",
            json={"error": "Unauthorized"},
            status=401,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"USPTO_TSDR_API_KEY": "bad-key"}):
                fetcher = USPTOTrademarksFetcher(data_dir=tmpdir)
            result = fetcher.fetch(serial_numbers=["90123456"])

        assert result["status"] == "failed"
        assert result["record_count"] == 0

    @responses.activate
    def test_fetch_api_error(self):
        """fetch() handles 500 server error."""
        responses.add(
            responses.GET,
            "https://tsdrapi.uspto.gov/ts/cd/caseMultiStatus/sn",
            json={"error": "Internal Server Error"},
            status=500,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"USPTO_TSDR_API_KEY": "test-key"}):
                fetcher = USPTOTrademarksFetcher(data_dir=tmpdir)
            result = fetcher.fetch(serial_numbers=["90123456"])

        assert result["status"] == "failed"
        assert result["record_count"] == 0

    @responses.activate
    def test_fetch_deduplicates(self):
        """fetch() deduplicates by serial_number."""
        dup_cases = [
            {**SAMPLE_TSDR_CASE, "serialNumber": "90123456"},
            {**SAMPLE_TSDR_CASE, "serialNumber": "90123456"},
            {**SAMPLE_TSDR_CASE, "serialNumber": "90999999"},
        ]
        responses.add(
            responses.GET,
            "https://tsdrapi.uspto.gov/ts/cd/caseMultiStatus/sn",
            json=dup_cases,
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"USPTO_TSDR_API_KEY": "test-key"}):
                fetcher = USPTOTrademarksFetcher(data_dir=tmpdir)
            result = fetcher.fetch(serial_numbers=["90123456", "90123456", "90999999"])

        assert result["record_count"] == 2

    @responses.activate
    def test_fetch_batching(self):
        """fetch() splits serial numbers into batches of BATCH_SIZE."""
        # Create enough serial numbers for 2 batches
        serial_numbers = [f"90{i:06d}" for i in range(BATCH_SIZE + 10)]

        # Both batches return results
        batch1_cases = [
            {**SAMPLE_TSDR_CASE, "serialNumber": sn}
            for sn in serial_numbers[:BATCH_SIZE]
        ]
        batch2_cases = [
            {**SAMPLE_TSDR_CASE, "serialNumber": sn}
            for sn in serial_numbers[BATCH_SIZE:]
        ]

        responses.add(
            responses.GET,
            "https://tsdrapi.uspto.gov/ts/cd/caseMultiStatus/sn",
            json=batch1_cases,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://tsdrapi.uspto.gov/ts/cd/caseMultiStatus/sn",
            json=batch2_cases,
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"USPTO_TSDR_API_KEY": "test-key"}):
                fetcher = USPTOTrademarksFetcher(data_dir=tmpdir)
            result = fetcher.fetch(serial_numbers=serial_numbers)

        assert result["status"] == "success"
        assert result["record_count"] == BATCH_SIZE + 10
        assert len(responses.calls) == 2

    def test_load_serial_numbers_from_db_failure(self, tmp_path):
        """_load_serial_numbers_from_db returns empty on connection error."""
        with patch.dict(os.environ, {"USPTO_TSDR_API_KEY": "key"}):
            fetcher = USPTOTrademarksFetcher(data_dir=str(tmp_path))

        # Without a real DB, this should return empty list gracefully
        result = fetcher._load_serial_numbers_from_db()
        assert result == []


# ---------------------------------------------------------------------------
# Tests: trademark normalization
# ---------------------------------------------------------------------------

class TestUSPTONormalization:
    """Tests for _normalize_trademark static method."""

    def test_normalize_full_case(self):
        """Full TSDR case normalizes correctly."""
        result = USPTOTrademarksFetcher._normalize_trademark(SAMPLE_TSDR_CASE)

        assert result is not None
        assert result["serial_number"] == "90123456"
        assert result["mark_element"] == "PHARMATEST"
        assert result["mark_type"] == "Word Mark"
        assert result["status"] == "Registered"
        assert result["status_code"] == 800
        assert result["filing_date"] == "2024-01-15"
        assert result["registration_number"] == "6789012"
        assert result["owner_name"] == "Pharma Corp Inc."
        assert result["owner_entity_type"] == "Corporation"
        assert result["nice_classes"] == [5]

    def test_normalize_minimal_case(self):
        """Minimal case normalizes with None optionals."""
        result = USPTOTrademarksFetcher._normalize_trademark(SAMPLE_TSDR_CASE_MINIMAL)

        assert result is not None
        assert result["serial_number"] == "90999999"
        assert result["mark_element"] is None
        assert result["nice_classes"] is None
        assert result["owner_name"] is None

    def test_normalize_missing_serial_number(self):
        """Case without serialNumber returns None."""
        result = USPTOTrademarksFetcher._normalize_trademark({"statusStr": "Filed"})
        assert result is None

    def test_normalize_multiple_nice_classes(self):
        """Multiple Nice classes from gsList are extracted and sorted."""
        raw = {
            "serialNumber": "90111111",
            "gsList": [
                {"internationalClasses": [42, 5]},
                {"internationalClasses": [10]},
            ],
        }
        result = USPTOTrademarksFetcher._normalize_trademark(raw)
        assert result["nice_classes"] == [5, 10, 42]

    def test_normalize_snake_case_fallback(self):
        """Snake_case field names work as fallback."""
        raw = {
            "serial_number": "90222222",
            "mark_element": "TESTMARK",
            "status": "Filed",
        }
        result = USPTOTrademarksFetcher._normalize_trademark(raw)
        assert result is not None
        assert result["serial_number"] == "90222222"
        assert result["mark_element"] == "TESTMARK"


# ---------------------------------------------------------------------------
# Validator tests: valid records
# ---------------------------------------------------------------------------

class TestUSPTOTrademarkRecordValid:
    """Tests for valid USPTOTrademarkRecord instances."""

    def test_full_record(self):
        """Fully populated record validates successfully."""
        record = USPTOTrademarkRecord(
            serial_number="90123456",
            mark_element="PHARMATEST",
            mark_type="Word Mark",
            status="Registered",
            status_code=800,
            status_date=date(2024, 6, 1),
            filing_date=date(2024, 1, 15),
            registration_number="6789012",
            registration_date=date(2024, 6, 1),
            nice_classes=[5],
            us_classes=["A"],
            owner_name="Pharma Corp Inc.",
            owner_entity_type="Corporation",
            goods_and_services="Pharmaceutical preparations",
            description_of_mark="Standard characters",
        )
        assert record.serial_number == "90123456"
        assert record.nice_classes == [5]
        assert record.owner_name == "Pharma Corp Inc."

    def test_minimal_record(self):
        """Minimal record with only required field."""
        record = USPTOTrademarkRecord(serial_number="90999999")
        assert record.serial_number == "90999999"
        assert record.mark_element is None
        assert record.status is None
        assert record.nice_classes is None

    def test_whitespace_stripped(self):
        """Whitespace in serial_number is stripped."""
        record = USPTOTrademarkRecord(serial_number="  90123456  ")
        assert record.serial_number == "90123456"


# ---------------------------------------------------------------------------
# Validator tests: invalid records
# ---------------------------------------------------------------------------

class TestUSPTOTrademarkRecordInvalid:
    """Tests for invalid USPTOTrademarkRecord instances."""

    def test_empty_serial_number(self):
        """Empty serial_number is rejected."""
        with pytest.raises(ValidationError):
            USPTOTrademarkRecord(serial_number="")

    def test_missing_serial_number(self):
        """Omitting serial_number raises ValidationError."""
        with pytest.raises(ValidationError):
            USPTOTrademarkRecord()

    def test_whitespace_only_serial_number(self):
        """Whitespace-only serial_number is rejected."""
        with pytest.raises(ValidationError):
            USPTOTrademarkRecord(serial_number="   ")
