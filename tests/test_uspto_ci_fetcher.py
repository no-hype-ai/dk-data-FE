"""Tests for USPTO CI fetcher and validator with mocked HTTP.

Feature: 011-datasource-integration
Task: T055-T057 — USPTO PatentsView CI source integration

Tests use mocked HTTP responses so no external network calls are made.
"""

import tempfile
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
import responses
from pydantic import ValidationError

from dk_data.ingestion.fetchers.uspto_ci import (
    PATENTSVIEW_API,
    USPTOCIFetcher,
)
from dk_data.ingestion.utils.validators import USPTOCIRecord


# ---------------------------------------------------------------------------
# Sample PatentsView API response fixtures
# ---------------------------------------------------------------------------

SAMPLE_PATENT = {
    "patent_number": "US-11234567-B2",
    "patent_title": "Pharmaceutical composition for treating cancer",
    "patent_abstract": "A novel composition comprising a CDK4/6 inhibitor.",
    "patent_date": "2026-02-01",
    "patent_num_claims": 20,
    "app_date": "2024-06-15",
    "inventors": [
        {"inventor_first_name": "John", "inventor_last_name": "Smith"},
        {"inventor_first_name": "Jane", "inventor_last_name": "Doe"},
    ],
    "assignees": [
        {"assignee_organization": "Pharma Corp"},
    ],
    "cpcs": [
        {"cpc_subgroup_id": "A61K31/00"},
        {"cpc_subgroup_id": "A61P35/00"},
    ],
}

SAMPLE_PATENT_MINIMAL = {
    "patent_number": "US-99999999-B1",
    "patent_title": "Minimal patent record",
    "patent_abstract": None,
    "patent_date": "2026-01-15",
    "patent_num_claims": 5,
}


def _make_patentsview_response(patents, total=None):
    """Build a mock PatentsView API response body."""
    return {
        "patents": patents,
        "total_patent_count": total or len(patents),
        "count": len(patents),
    }


# ---------------------------------------------------------------------------
# Fetcher initialisation tests
# ---------------------------------------------------------------------------

class TestUSPTOCIFetcherInit:
    """Tests for fetcher initialization."""

    def test_fetcher_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = USPTOCIFetcher(data_dir=tmpdir)
            assert fetcher.SOURCE_NAME == "uspto_ci"
            assert fetcher.BASE_URL == "https://api.patentsview.org"
            assert fetcher.session is not None

    def test_fetcher_init_defaults(self):
        fetcher = USPTOCIFetcher()
        assert fetcher.SOURCE_NAME == "uspto_ci"
        assert fetcher.data_dir.exists()

    def test_get_latest_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = USPTOCIFetcher(data_dir=tmpdir)
            url = fetcher.get_latest_url()
            assert url == PATENTSVIEW_API
            assert "patentsview" in url


# ---------------------------------------------------------------------------
# Fetch with mocked HTTP
# ---------------------------------------------------------------------------

class TestUSPTOCIFetch:
    """Tests for the fetch method with mocked HTTP responses."""

    @responses.activate
    def test_fetch_success(self):
        """Full happy-path: API returns patent results."""
        responses.add(
            responses.GET,
            PATENTSVIEW_API,
            json=_make_patentsview_response(
                [SAMPLE_PATENT, SAMPLE_PATENT_MINIMAL]
            ),
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = USPTOCIFetcher(data_dir=tmpdir)
            result = fetcher.fetch(
                search_terms=["cancer", "CDK4"],
                days_back=7,
            )

        assert result["status"] == "success"
        assert len(result["records"]) == 2
        assert result["hash"] is not None

        # Verify first patent record
        rec = result["records"][0]
        assert rec["patent_id"] == "US-11234567-B2"
        assert rec["title"] == "Pharmaceutical composition for treating cancer"
        assert "CDK4/6 inhibitor" in rec["abstract"]
        assert rec["grant_date"] == "2026-02-01"
        assert rec["claims_count"] == 20
        assert rec["inventors"] is not None

    @responses.activate
    def test_fetch_empty_results(self):
        """API returns zero results."""
        responses.add(
            responses.GET,
            PATENTSVIEW_API,
            json=_make_patentsview_response([]),
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = USPTOCIFetcher(data_dir=tmpdir)
            result = fetcher.fetch(
                search_terms=["nonexistent_drug_xyz"],
                days_back=7,
            )

        assert result["status"] == "success"
        assert result["records"] == []
        assert result["hash"] is None

    @responses.activate
    def test_fetch_api_error(self):
        """API returns a 500 error."""
        responses.add(
            responses.GET,
            PATENTSVIEW_API,
            json={"error": "Internal Server Error"},
            status=500,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = USPTOCIFetcher(data_dir=tmpdir)
            result = fetcher.fetch(
                search_terms=["cancer"],
                days_back=7,
            )

        # Individual page errors are caught; overall fetch succeeds with 0 records
        assert result["status"] == "success"
        assert result["records"] == []

    def test_fetch_no_search_terms(self):
        """Fetch with no search terms returns empty success."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = USPTOCIFetcher(data_dir=tmpdir)
            result = fetcher.fetch(search_terms=[])

        assert result["status"] == "success"
        assert result["records"] == []

    @responses.activate
    def test_fetch_pagination(self):
        """Pagination stops when fewer results than page size returned."""
        # Page 1: full page (100 patents)
        page1_patents = [
            {**SAMPLE_PATENT, "patent_number": f"US-{i:08d}-B2"}
            for i in range(100)
        ]
        # Page 2: partial page
        page2_patents = [
            {**SAMPLE_PATENT, "patent_number": f"US-P2-{i:04d}-B2"}
            for i in range(10)
        ]

        responses.add(
            responses.GET,
            PATENTSVIEW_API,
            json=_make_patentsview_response(page1_patents),
            status=200,
        )
        responses.add(
            responses.GET,
            PATENTSVIEW_API,
            json=_make_patentsview_response(page2_patents),
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = USPTOCIFetcher(data_dir=tmpdir)
            result = fetcher.fetch(
                search_terms=["cancer"],
                days_back=30,
            )

        assert result["status"] == "success"
        assert len(result["records"]) == 110
        assert len(responses.calls) == 2

    @responses.activate
    def test_fetch_deduplication(self):
        """Duplicate patent IDs are deduplicated."""
        # Same patent returned twice
        responses.add(
            responses.GET,
            PATENTSVIEW_API,
            json=_make_patentsview_response([SAMPLE_PATENT, SAMPLE_PATENT]),
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = USPTOCIFetcher(data_dir=tmpdir)
            result = fetcher.fetch(
                search_terms=["cancer"],
                days_back=7,
            )

        assert result["status"] == "success"
        assert len(result["records"]) == 1


# ---------------------------------------------------------------------------
# Query building tests
# ---------------------------------------------------------------------------

class TestQueryBuilding:
    """Tests for the PatentsView query builder."""

    def test_build_query_structure(self):
        query = USPTOCIFetcher._build_query(
            ["pembrolizumab", "oncology"], "2026-01-01"
        )
        assert "_and" in query
        and_clauses = query["_and"]
        assert len(and_clauses) == 3

        # Date clause
        assert "_gte" in and_clauses[0]
        assert and_clauses[0]["_gte"]["patent_date"] == "2026-01-01"

        # CPC clause
        assert "_or" in and_clauses[1]

        # Text clause
        assert "_or" in and_clauses[2]

    def test_build_query_single_term(self):
        query = USPTOCIFetcher._build_query(["semaglutide"], "2026-02-01")
        text_clauses = query["_and"][2]["_or"]
        assert len(text_clauses) == 1


# ---------------------------------------------------------------------------
# Patent normalisation tests
# ---------------------------------------------------------------------------

class TestPatentNormalization:
    """Tests for patent record normalization."""

    def test_normalize_full_patent(self):
        record = USPTOCIFetcher._normalize_patent(SAMPLE_PATENT)
        assert record is not None
        assert record["patent_id"] == "US-11234567-B2"
        assert record["title"] == "Pharmaceutical composition for treating cancer"
        assert record["grant_date"] == "2026-02-01"
        assert record["filing_date"] == "2024-06-15"
        assert record["claims_count"] == 20

    def test_normalize_minimal_patent(self):
        record = USPTOCIFetcher._normalize_patent(SAMPLE_PATENT_MINIMAL)
        assert record is not None
        assert record["patent_id"] == "US-99999999-B1"
        assert record["inventors"] is None
        assert record["assignees"] is None

    def test_normalize_missing_number(self):
        record = USPTOCIFetcher._normalize_patent({})
        assert record is None


# ---------------------------------------------------------------------------
# USPTOCIRecord validator tests
# ---------------------------------------------------------------------------

class TestUSPTOCIRecord:
    """Tests for the USPTOCIRecord Pydantic model."""

    def test_valid_record(self):
        record = USPTOCIRecord(
            patent_id="US-11234567-B2",
            title="Pharmaceutical composition",
            abstract="A novel composition.",
            inventors=[{"first": "John", "last": "Smith"}],
            assignees=[{"org": "Pharma Corp"}],
            filing_date=date(2024, 6, 15),
            grant_date=date(2026, 2, 1),
            cpc_codes=["A61K31/00", "A61P35/00"],
            claims_count=20,
        )
        assert record.patent_id == "US-11234567-B2"
        assert len(record.cpc_codes) == 2
        assert record.claims_count == 20

    def test_minimal_record(self):
        record = USPTOCIRecord(patent_id="US-00000001-B1")
        assert record.patent_id == "US-00000001-B1"
        assert record.title is None
        assert record.inventors is None
        assert record.cpc_codes is None

    def test_empty_patent_id_rejected(self):
        with pytest.raises(ValidationError):
            USPTOCIRecord(patent_id="")

    def test_missing_patent_id_rejected(self):
        with pytest.raises(ValidationError):
            USPTOCIRecord()

    def test_negative_claims_count_rejected(self):
        with pytest.raises(ValidationError):
            USPTOCIRecord(patent_id="US-001", claims_count=-1)

    def test_zero_claims_count_valid(self):
        record = USPTOCIRecord(patent_id="US-001", claims_count=0)
        assert record.claims_count == 0

    def test_whitespace_stripped(self):
        record = USPTOCIRecord(patent_id="  US-12345  ")
        assert record.patent_id == "US-12345"
