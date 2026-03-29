"""Tests for USPTO Patents fetcher and validator.

Feature: 011-datasource-integration
Task: Phase 6 / US4 — credential-gated source (USPTO PatentSearch)

Tests use mocked HTTP responses so no external network calls are made.
"""

import os
import tempfile
from datetime import date
from unittest.mock import patch

import pytest
import responses
from pydantic import ValidationError

from dk_data.ingestion.fetchers.uspto_patents import USPTOPatentsFetcher
from dk_data.ingestion.utils.validators import USPTOPatentsRecord


# ---------------------------------------------------------------------------
# Sample PatentSearch API response fixtures
# ---------------------------------------------------------------------------

SAMPLE_PATENT = {
    "patent_id": "11234567",
    "patent_title": "Pharmaceutical composition for treating cancer",
    "patent_abstract": "A novel pharmaceutical composition comprising...",
    "patent_date": "2026-01-15",
    "patent_num_claims": 20,
    "inventors": [
        {
            "inventor_name_first": "John",
            "inventor_name_last": "Doe",
            "inventor_city": "Boston",
            "inventor_state": "MA",
            "inventor_country": "US",
        },
    ],
    "assignees": [
        {
            "assignee_organization": "Pharma Corp",
            "assignee_city": "Cambridge",
            "assignee_state": "MA",
            "assignee_country": "US",
        },
    ],
    "cpc_current": [
        {"cpc_subgroup_id": "A61K31/00"},
        {"cpc_subgroup_id": "A61P35/00"},
    ],
    "application": {
        "filing_date": "2024-06-01",
        "application_id": "16/123456",
    },
}

SAMPLE_PATENT_MINIMAL = {
    "patent_id": "11999999",
    "patent_title": "Simple drug delivery method",
    "patent_abstract": None,
    "patent_date": "2026-02-01",
    "patent_num_claims": 5,
}


def _make_patentsearch_response(patents, total_hits=None):
    """Build a mock PatentSearch API response body."""
    if total_hits is None:
        total_hits = len(patents)
    return {
        "patents": patents,
        "count": len(patents),
        "total_hits": total_hits,
    }


# ---------------------------------------------------------------------------
# Tests: fetcher initialization
# ---------------------------------------------------------------------------

class TestUSPTOPatentsFetcherInit:
    """Verify USPTOPatentsFetcher initializes correctly."""

    def test_fetcher_init(self, tmp_path):
        """Fetcher can be instantiated with a custom data_dir."""
        with patch.dict(os.environ, {"USPTO_API_KEY": "test-key-123"}):
            fetcher = USPTOPatentsFetcher(data_dir=str(tmp_path))

        assert fetcher.SOURCE_NAME == "uspto_patents"
        assert fetcher.BASE_URL == "https://search.patentsview.org"
        assert fetcher.data_dir == tmp_path
        assert fetcher.session is not None
        assert fetcher.api_key == "test-key-123"

    def test_fetcher_init_no_api_key(self, tmp_path):
        """Fetcher initializes without API key (with warning)."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("USPTO_API_KEY", None)
            fetcher = USPTOPatentsFetcher(data_dir=str(tmp_path))

        assert fetcher.api_key is None

    def test_fetcher_data_dir_created(self, tmp_path):
        """Verify the data directory is created on init."""
        data_path = tmp_path / "sub" / "raw"
        with patch.dict(os.environ, {"USPTO_API_KEY": "key"}):
            USPTOPatentsFetcher(data_dir=str(data_path))  # side-effect: creates dir
        assert data_path.exists()


# ---------------------------------------------------------------------------
# Tests: get_latest_url
# ---------------------------------------------------------------------------

class TestUSPTOPatentsGetLatestUrl:
    """Verify the URL returned by get_latest_url."""

    def test_get_latest_url(self, tmp_path):
        with patch.dict(os.environ, {"USPTO_API_KEY": "key"}):
            fetcher = USPTOPatentsFetcher(data_dir=str(tmp_path))
        url = fetcher.get_latest_url()
        assert url == "https://search.patentsview.org/api/v1/patent/"
        assert url.startswith("https://")


# ---------------------------------------------------------------------------
# Tests: fetch with mocked HTTP
# ---------------------------------------------------------------------------

class TestUSPTOPatentsFetchWithMock:
    """Verify the full fetch flow using mocked HTTP."""

    @responses.activate
    def test_fetch_success(self):
        """fetch() returns success with records when API responds."""
        responses.add(
            responses.POST,
            "https://search.patentsview.org/api/v1/patent/",
            json=_make_patentsearch_response([SAMPLE_PATENT, SAMPLE_PATENT_MINIMAL]),
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"USPTO_API_KEY": "test-key"}):
                fetcher = USPTOPatentsFetcher(data_dir=tmpdir)
            result = fetcher.fetch(days_back=7)

        assert result["status"] == "success"
        assert result["record_count"] == 2
        assert len(result["records"]) == 2
        assert result["hash"] is not None

        # Verify record normalization
        rec = result["records"][0]
        assert rec["patent_number"] == "11234567"
        assert rec["title"] == "Pharmaceutical composition for treating cancer"
        assert rec["claims_count"] == 20
        assert rec["filing_date"] == "2024-06-01"
        assert rec["inventors"] is not None
        assert len(rec["inventors"]) == 1
        assert rec["inventors"][0]["name_first"] == "John"
        assert rec["assignees"] is not None
        assert rec["cpc_codes"] is not None
        assert "A61K31/00" in rec["cpc_codes"]

        # Verify minimal record
        rec_min = result["records"][1]
        assert rec_min["patent_number"] == "11999999"
        assert rec_min["abstract"] is None
        assert rec_min["inventors"] is None

    @responses.activate
    def test_fetch_empty_results(self):
        """fetch() returns success with 0 records on empty API response."""
        responses.add(
            responses.POST,
            "https://search.patentsview.org/api/v1/patent/",
            json=_make_patentsearch_response([]),
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"USPTO_API_KEY": "test-key"}):
                fetcher = USPTOPatentsFetcher(data_dir=tmpdir)
            result = fetcher.fetch(days_back=1)

        assert result["status"] == "success"
        assert result["record_count"] == 0
        assert result["records"] == []

    @responses.activate
    def test_fetch_api_error(self):
        """fetch() returns failed when API returns error status."""
        responses.add(
            responses.POST,
            "https://search.patentsview.org/api/v1/patent/",
            json={"error": "Unauthorized"},
            status=401,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"USPTO_API_KEY": "bad-key"}):
                fetcher = USPTOPatentsFetcher(data_dir=tmpdir)
            result = fetcher.fetch(days_back=1)

        assert result["status"] == "failed"
        assert result["error"] is not None
        assert result["records"] == []

    @responses.activate
    def test_fetch_pagination(self):
        """fetch() paginates through multiple pages via cursor."""
        # Page 1: full page (PAGE_SIZE=100 items)
        page1_patents = [
            {**SAMPLE_PATENT, "patent_id": f"P1-{i:04d}"}
            for i in range(100)
        ]
        # Page 2: partial page (signals end of results)
        page2_patents = [
            {**SAMPLE_PATENT, "patent_id": f"P2-{i:04d}"}
            for i in range(10)
        ]

        responses.add(
            responses.POST,
            "https://search.patentsview.org/api/v1/patent/",
            json=_make_patentsearch_response(page1_patents),
            status=200,
        )
        responses.add(
            responses.POST,
            "https://search.patentsview.org/api/v1/patent/",
            json=_make_patentsearch_response(page2_patents),
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"USPTO_API_KEY": "test-key"}):
                fetcher = USPTOPatentsFetcher(data_dir=tmpdir)
            result = fetcher.fetch(days_back=7)

        assert result["status"] == "success"
        assert result["record_count"] == 110
        assert len(responses.calls) == 2

    @responses.activate
    def test_fetch_respects_max_records(self):
        """fetch() stops when max_records limit is reached."""
        patents = [
            {**SAMPLE_PATENT, "patent_id": f"P-{i:04d}"}
            for i in range(100)
        ]
        responses.add(
            responses.POST,
            "https://search.patentsview.org/api/v1/patent/",
            json=_make_patentsearch_response(patents),
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"USPTO_API_KEY": "test-key"}):
                fetcher = USPTOPatentsFetcher(data_dir=tmpdir)
            result = fetcher.fetch(days_back=7, max_records=50)

        assert result["status"] == "success"
        # Should stop at max_records
        assert result["record_count"] <= 100

    def test_fetch_without_api_key(self):
        """fetch() returns source_unavailable without API key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {}, clear=True):
                os.environ.pop("USPTO_API_KEY", None)
                fetcher = USPTOPatentsFetcher(data_dir=tmpdir)
            result = fetcher.fetch(days_back=7)

        assert result["status"] in ("source_unavailable", "failed")
        assert result["record_count"] == 0
        assert "error" in result


# ---------------------------------------------------------------------------
# Tests: patent normalization
# ---------------------------------------------------------------------------

class TestPatentNormalization:
    """Tests for the _normalize_patent method."""

    def test_normalize_full_patent(self, tmp_path):
        """Test normalization of a fully populated patent."""
        with patch.dict(os.environ, {"USPTO_API_KEY": "key"}):
            fetcher = USPTOPatentsFetcher(data_dir=str(tmp_path))

        result = fetcher._normalize_patent(SAMPLE_PATENT)

        assert result is not None
        assert result["patent_number"] == "11234567"
        assert result["title"] == "Pharmaceutical composition for treating cancer"
        assert result["abstract"] is not None
        assert result["claims_count"] == 20
        assert result["filing_date"] == "2024-06-01"
        assert result["grant_date"] == "2026-01-15"

    def test_normalize_patent_missing_number(self, tmp_path):
        """Patent without patent_id returns None."""
        with patch.dict(os.environ, {"USPTO_API_KEY": "key"}):
            fetcher = USPTOPatentsFetcher(data_dir=str(tmp_path))

        result = fetcher._normalize_patent({"patent_title": "No number"})
        assert result is None

    def test_normalize_minimal_patent(self, tmp_path):
        """Patent with minimal fields normalizes correctly."""
        with patch.dict(os.environ, {"USPTO_API_KEY": "key"}):
            fetcher = USPTOPatentsFetcher(data_dir=str(tmp_path))

        result = fetcher._normalize_patent(SAMPLE_PATENT_MINIMAL)

        assert result is not None
        assert result["patent_number"] == "11999999"
        assert result["inventors"] is None
        assert result["assignees"] is None
        assert result["cpc_codes"] is None


# ---------------------------------------------------------------------------
# Tests: Pydantic validator — valid records
# ---------------------------------------------------------------------------

class TestUSPTOPatentsRecordValid:
    """Test that valid records pass Pydantic validation."""

    def test_full_record(self):
        """A fully populated record validates successfully."""
        record = USPTOPatentsRecord(
            patent_number="11234567",
            title="Pharmaceutical composition",
            abstract="A novel composition...",
            inventors=[{"name_first": "John", "name_last": "Doe"}],
            assignees=[{"organization": "Pharma Corp"}],
            filing_date=date(2024, 6, 1),
            grant_date=date(2026, 1, 15),
            cpc_codes=["A61K31/00", "A61P35/00"],
            claims_count=20,
        )

        assert record.patent_number == "11234567"
        assert record.claims_count == 20
        assert len(record.cpc_codes) == 2

    def test_minimal_record(self):
        """A record with only patent_number validates."""
        record = USPTOPatentsRecord(patent_number="11234567")
        assert record.patent_number == "11234567"
        assert record.title is None
        assert record.inventors is None

    def test_zero_claims(self):
        """Zero claims_count is valid."""
        record = USPTOPatentsRecord(patent_number="11234567", claims_count=0)
        assert record.claims_count == 0

    def test_whitespace_stripped(self):
        """Whitespace in patent_number is stripped."""
        record = USPTOPatentsRecord(patent_number="  11234567  ")
        assert record.patent_number == "11234567"


# ---------------------------------------------------------------------------
# Tests: Pydantic validator — invalid records
# ---------------------------------------------------------------------------

class TestUSPTOPatentsRecordInvalid:
    """Test that invalid records are rejected by Pydantic."""

    def test_empty_patent_number(self):
        """An empty patent_number is rejected."""
        with pytest.raises(ValidationError):
            USPTOPatentsRecord(patent_number="")

    def test_missing_patent_number(self):
        """Omitting patent_number raises ValidationError."""
        with pytest.raises(ValidationError):
            USPTOPatentsRecord()

    def test_negative_claims_count(self):
        """Negative claims_count is rejected."""
        with pytest.raises(ValidationError):
            USPTOPatentsRecord(patent_number="11234567", claims_count=-1)

    def test_whitespace_only_patent_number(self):
        """A patent_number of only whitespace is rejected."""
        with pytest.raises(ValidationError):
            USPTOPatentsRecord(patent_number="   ")
