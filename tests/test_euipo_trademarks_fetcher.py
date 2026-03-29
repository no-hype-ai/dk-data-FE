"""Tests for EUIPO Trademarks Fetcher and EUIPOTrademarkRecord validator.

Feature: 014-uspto-euipo-model-datasource
Task: T025 — EUIPO trademark fetcher tests

Tests cover:
- Fetcher initialization (TMview and IBM Gateway backends)
- get_latest_url for each backend
- TMview fetch with mocked HTTP (success, empty, pagination, error)
- IBM Gateway fetch with OAuth2 token flow
- Trademark normalization
- EUIPOTrademarkRecord Pydantic validation (valid and invalid)
"""

import os
import tempfile
from datetime import date
from unittest.mock import patch

import pytest
import responses
from pydantic import ValidationError

from dk_data.ingestion.fetchers.euipo_trademarks import (
    EUIPOTrademarksFetcher,
    PAGE_SIZE,
)
from dk_data.ingestion.utils.validators import EUIPOTrademarkRecord


# ---------------------------------------------------------------------------
# Sample TMview API response fixtures
# ---------------------------------------------------------------------------

SAMPLE_TRADEMARK = {
    "applicationNumber": "018123456",
    "tradeMarkName": "PHARMATEST",
    "tradeMarkType": "Word",
    "markFeature": "Standard",
    "markBasis": "EUTM",
    "applicantName": "Pharma Corp GmbH",
    "applicantCountry": "DE",
    "representativeName": "IP Attorneys LLP",
    "status": "Registered",
    "applicationDate": "2024-01-15",
    "registrationDate": "2024-06-01",
    "expiryDate": "2034-01-15",
    "niceClasses": [5, 10],
    "goodsAndServices": "Pharmaceutical preparations",
    "imageUrl": "https://tmview.example.com/img/018123456.png",
}

SAMPLE_TRADEMARK_MINIMAL = {
    "applicationNumber": "018999999",
    "status": "Filed",
}

IBM_TOKEN_RESPONSE = {
    "access_token": "ibm_test_token_abc123",
    "token_type": "Bearer",
    "expires_in": 3600,
}


def _make_tmview_response(trademarks, total=None):
    """Build a mock TMview API response."""
    return {
        "tradeMarks": trademarks,
        "totalResults": total if total is not None else len(trademarks),
    }


# ---------------------------------------------------------------------------
# Tests: fetcher initialization
# ---------------------------------------------------------------------------

class TestEUIPOFetcherInit:
    """Tests for EUIPO fetcher initialization."""

    def test_fetcher_init_tmview_default(self, tmp_path):
        """Fetcher defaults to TMview backend."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("EUIPO_BACKEND", None)
            os.environ.pop("EUIPO_API_KEY", None)
            os.environ.pop("EUIPO_SECRET_KEY", None)
            fetcher = EUIPOTrademarksFetcher(data_dir=str(tmp_path))

        assert fetcher.SOURCE_NAME == "euipo_trademarks"
        assert fetcher.backend == "tmview"
        assert fetcher.session is not None

    def test_fetcher_init_tmview_explicit(self, tmp_path):
        """Fetcher uses TMview when explicitly set."""
        with patch.dict(os.environ, {"EUIPO_BACKEND": "tmview"}, clear=True):
            fetcher = EUIPOTrademarksFetcher(data_dir=str(tmp_path))
        assert fetcher.backend == "tmview"

    def test_fetcher_init_ibm_gateway(self, tmp_path):
        """Fetcher uses IBM Gateway when set with credentials."""
        with patch.dict(os.environ, {
            "EUIPO_BACKEND": "ibm_gateway",
            "EUIPO_API_KEY": "test_key",
            "EUIPO_SECRET_KEY": "test_secret",
        }):
            fetcher = EUIPOTrademarksFetcher(data_dir=str(tmp_path))

        assert fetcher.backend == "ibm_gateway"
        assert fetcher.api_key == "test_key"
        assert fetcher.secret_key == "test_secret"

    def test_fetcher_ibm_fallback_without_credentials(self, tmp_path):
        """IBM Gateway falls back to TMview without credentials."""
        with patch.dict(os.environ, {"EUIPO_BACKEND": "ibm_gateway"}, clear=True):
            os.environ.pop("EUIPO_API_KEY", None)
            os.environ.pop("EUIPO_SECRET_KEY", None)
            fetcher = EUIPOTrademarksFetcher(data_dir=str(tmp_path))

        assert fetcher.backend == "tmview"

    def test_fetcher_init_with_backend_arg(self, tmp_path):
        """Backend argument overrides environment."""
        with patch.dict(os.environ, {"EUIPO_BACKEND": "tmview"}, clear=True):
            fetcher = EUIPOTrademarksFetcher(
                data_dir=str(tmp_path), backend="tmview"
            )
        assert fetcher.backend == "tmview"


# ---------------------------------------------------------------------------
# Tests: get_latest_url
# ---------------------------------------------------------------------------

class TestEUIPOFetcherURL:
    """Tests for get_latest_url based on backend."""

    def test_get_latest_url_tmview(self, tmp_path):
        """TMview returns the TMview search URL."""
        with patch.dict(os.environ, {}, clear=True):
            fetcher = EUIPOTrademarksFetcher(data_dir=str(tmp_path))
        url = fetcher.get_latest_url()
        assert "tmdn.org" in url
        assert "api/search" in url

    def test_get_latest_url_ibm_gateway(self, tmp_path):
        """IBM Gateway returns the EUIPO API URL."""
        with patch.dict(os.environ, {
            "EUIPO_BACKEND": "ibm_gateway",
            "EUIPO_API_KEY": "k",
            "EUIPO_SECRET_KEY": "s",
        }):
            fetcher = EUIPOTrademarksFetcher(data_dir=str(tmp_path))
        url = fetcher.get_latest_url()
        assert "api.euipo.europa.eu" in url


# ---------------------------------------------------------------------------
# Tests: TMview fetch with mocked HTTP
# ---------------------------------------------------------------------------

class TestEUIPOFetchTMview:
    """Tests for TMview fetch with mocked HTTP responses."""

    @responses.activate
    def test_fetch_success(self):
        """fetch() returns success with normalized records."""
        responses.add(
            responses.POST,
            "https://www.tmdn.org/tmview/api/search",
            json=_make_tmview_response([SAMPLE_TRADEMARK, SAMPLE_TRADEMARK_MINIMAL]),
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {}, clear=True):
                fetcher = EUIPOTrademarksFetcher(data_dir=tmpdir)
            result = fetcher.fetch(nice_classes=["05"], days_back=7)

        assert result["status"] == "success"
        assert result["record_count"] == 2
        assert len(result["records"]) == 2
        assert result["hash"] is not None

        rec = result["records"][0]
        assert rec["application_number"] == "018123456"
        assert rec["mark_name"] == "PHARMATEST"
        assert rec["applicant_name"] == "Pharma Corp GmbH"
        assert rec["nice_classes"] == [5, 10]

    @responses.activate
    def test_fetch_empty_results(self):
        """fetch() returns success with 0 records on empty response."""
        responses.add(
            responses.POST,
            "https://www.tmdn.org/tmview/api/search",
            json=_make_tmview_response([]),
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {}, clear=True):
                fetcher = EUIPOTrademarksFetcher(data_dir=tmpdir)
            result = fetcher.fetch(days_back=1)

        assert result["status"] == "success"
        assert result["record_count"] == 0
        assert result["records"] == []

    @responses.activate
    def test_fetch_api_error(self):
        """fetch() returns failed or source_unavailable on unrecoverable API error."""
        responses.add(
            responses.POST,
            "https://www.tmdn.org/tmview/api/search",
            json={"error": "Service unavailable"},
            status=500,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {}, clear=True):
                fetcher = EUIPOTrademarksFetcher(data_dir=tmpdir)
            result = fetcher.fetch(days_back=1)

        assert result["status"] in ("failed", "source_unavailable")
        assert result["record_count"] == 0

    @responses.activate
    def test_fetch_pagination(self):
        """fetch() paginates through multiple pages."""
        page1 = [
            {**SAMPLE_TRADEMARK, "applicationNumber": f"018{i:06d}"}
            for i in range(PAGE_SIZE)
        ]
        page2 = [
            {**SAMPLE_TRADEMARK, "applicationNumber": f"019{i:06d}"}
            for i in range(10)
        ]

        responses.add(
            responses.POST,
            "https://www.tmdn.org/tmview/api/search",
            json=_make_tmview_response(page1),
            status=200,
        )
        responses.add(
            responses.POST,
            "https://www.tmdn.org/tmview/api/search",
            json=_make_tmview_response(page2),
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {}, clear=True):
                fetcher = EUIPOTrademarksFetcher(data_dir=tmpdir)
            result = fetcher.fetch(days_back=30, max_records=10000)

        assert result["status"] == "success"
        assert result["record_count"] == PAGE_SIZE + 10
        assert len(responses.calls) == 2

    @responses.activate
    def test_fetch_deduplicates(self):
        """fetch() deduplicates by application_number."""
        dup_trademarks = [
            {**SAMPLE_TRADEMARK, "applicationNumber": "018123456"},
            {**SAMPLE_TRADEMARK, "applicationNumber": "018123456"},
            {**SAMPLE_TRADEMARK, "applicationNumber": "018999999"},
        ]

        responses.add(
            responses.POST,
            "https://www.tmdn.org/tmview/api/search",
            json=_make_tmview_response(dup_trademarks),
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {}, clear=True):
                fetcher = EUIPOTrademarksFetcher(data_dir=tmpdir)
            result = fetcher.fetch(days_back=7)

        assert result["record_count"] == 2


# ---------------------------------------------------------------------------
# Tests: IBM Gateway fetch with OAuth2
# ---------------------------------------------------------------------------

class TestEUIPOFetchIBMGateway:
    """Tests for IBM Gateway fetch with OAuth2 token flow."""

    @responses.activate
    def test_ibm_gateway_fetch_success(self):
        """IBM Gateway fetch obtains token then queries API."""
        # OAuth token
        responses.add(
            responses.POST,
            "https://auth.euipo.europa.eu/oidc/accessToken",
            json=IBM_TOKEN_RESPONSE,
            status=200,
        )
        # Search results
        responses.add(
            responses.GET,
            "https://api.euipo.europa.eu/trademark-search/trademarks",
            json=_make_tmview_response([SAMPLE_TRADEMARK]),
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {
                "EUIPO_BACKEND": "ibm_gateway",
                "EUIPO_API_KEY": "test_key",
                "EUIPO_SECRET_KEY": "test_secret",
            }):
                fetcher = EUIPOTrademarksFetcher(data_dir=tmpdir)
            result = fetcher.fetch(days_back=7)

        assert result["status"] == "success"
        assert result["record_count"] == 1
        assert result["records"][0]["application_number"] == "018123456"

    def test_ibm_ensure_token_missing_credentials(self, tmp_path):
        """_ensure_ibm_token raises without credentials."""
        with patch.dict(os.environ, {}, clear=True):
            fetcher = EUIPOTrademarksFetcher(data_dir=str(tmp_path))
            fetcher.backend = "ibm_gateway"
            fetcher.api_key = None
            fetcher.secret_key = None

        with pytest.raises(RuntimeError, match="EUIPO_API_KEY"):
            fetcher._ensure_ibm_token()


# ---------------------------------------------------------------------------
# Tests: trademark normalization
# ---------------------------------------------------------------------------

class TestEUIPONormalization:
    """Tests for _normalize_trademark static method."""

    def test_normalize_full_trademark(self):
        """Full TMview record normalizes correctly."""
        result = EUIPOTrademarksFetcher._normalize_trademark(SAMPLE_TRADEMARK)

        assert result is not None
        assert result["application_number"] == "018123456"
        assert result["mark_name"] == "PHARMATEST"
        assert result["mark_kind"] == "Word"
        assert result["applicant_name"] == "Pharma Corp GmbH"
        assert result["applicant_country"] == "DE"
        assert result["status"] == "Registered"
        assert result["nice_classes"] == [5, 10]

    def test_normalize_minimal_trademark(self):
        """Minimal record normalizes with None optionals."""
        result = EUIPOTrademarksFetcher._normalize_trademark(SAMPLE_TRADEMARK_MINIMAL)

        assert result is not None
        assert result["application_number"] == "018999999"
        assert result["mark_name"] is None
        assert result["nice_classes"] is None

    def test_normalize_missing_application_number(self):
        """Record without application_number returns None."""
        result = EUIPOTrademarksFetcher._normalize_trademark({"status": "Filed"})
        assert result is None

    def test_normalize_nice_classes_as_strings(self):
        """Nice classes provided as strings are converted to integers."""
        raw = {
            "applicationNumber": "018555555",
            "niceClasses": ["5", "10", "42"],
        }
        result = EUIPOTrademarksFetcher._normalize_trademark(raw)
        assert result["nice_classes"] == [5, 10, 42]

    def test_normalize_st13_fallback(self):
        """ST13 identifier is used as fallback for application_number."""
        raw = {"ST13": "EM018777777"}
        result = EUIPOTrademarksFetcher._normalize_trademark(raw)
        assert result is not None
        assert result["application_number"] == "EM018777777"


# ---------------------------------------------------------------------------
# Validator tests: valid records
# ---------------------------------------------------------------------------

class TestEUIPOTrademarkRecordValid:
    """Tests for valid EUIPOTrademarkRecord instances."""

    def test_full_record(self):
        """Fully populated record validates successfully."""
        record = EUIPOTrademarkRecord(
            application_number="018123456",
            mark_name="PHARMATEST",
            mark_kind="Word",
            mark_feature="Standard",
            mark_basis="EUTM",
            applicant_name="Pharma Corp GmbH",
            applicant_country="DE",
            representative_name="IP Attorneys LLP",
            status="Registered",
            filing_date=date(2024, 1, 15),
            registration_date=date(2024, 6, 1),
            expiry_date=date(2034, 1, 15),
            nice_classes=[5, 10],
            goods_and_services="Pharmaceutical preparations",
        )
        assert record.application_number == "018123456"
        assert record.mark_name == "PHARMATEST"
        assert record.nice_classes == [5, 10]

    def test_minimal_record(self):
        """Minimal record with only required field."""
        record = EUIPOTrademarkRecord(application_number="018999999")
        assert record.application_number == "018999999"
        assert record.mark_name is None
        assert record.status is None
        assert record.nice_classes is None

    def test_whitespace_stripped(self):
        """Whitespace in application_number is stripped."""
        record = EUIPOTrademarkRecord(application_number="  018123456  ")
        assert record.application_number == "018123456"


# ---------------------------------------------------------------------------
# Validator tests: invalid records
# ---------------------------------------------------------------------------

class TestEUIPOTrademarkRecordInvalid:
    """Tests for invalid EUIPOTrademarkRecord instances."""

    def test_empty_application_number(self):
        """Empty application_number is rejected."""
        with pytest.raises(ValidationError):
            EUIPOTrademarkRecord(application_number="")

    def test_missing_application_number(self):
        """Omitting application_number raises ValidationError."""
        with pytest.raises(ValidationError):
            EUIPOTrademarkRecord()

    def test_whitespace_only_application_number(self):
        """Whitespace-only application_number is rejected."""
        with pytest.raises(ValidationError):
            EUIPOTrademarkRecord(application_number="   ")
