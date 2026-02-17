"""Tests for SEC EDGAR Fetcher and SECEdgarRecord validator.

Feature: 011-datasource-integration
Task: T070-T072 — SEC EDGAR pharmaceutical filings

Tests cover:
- Fetcher initialization and User-Agent configuration
- get_latest_url endpoint
- Full fetch with mocked EDGAR API
- Filing normalization and SIC filtering
- SECEdgarRecord validation (valid and invalid)
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from dk_data.ingestion.fetchers.sec_edgar import (
    SECEdgarFetcher,
    PHARMA_SIC_CODES,
    DEFAULT_SEC_USER_AGENT,
)
from dk_data.ingestion.utils.validators import SECEdgarRecord


# ---------------------------------------------------------------------------
# Sample EDGAR API response fixtures
# ---------------------------------------------------------------------------

SAMPLE_EDGAR_RESPONSE = {
    "hits": {
        "hits": [
            {
                "_id": "0001234567-26-000123",
                "_source": {
                    "accession_number": "0001234567-26-000123",
                    "company_name": "Pfizer Inc",
                    "cik": "78003",
                    "filing_date": "2026-02-01",
                    "file_url": "https://www.sec.gov/Archives/edgar/data/78003/000123456726000123/pfizer-10k.htm",
                    "file_description": "Annual Report",
                    "sic": "2834",
                },
            },
            {
                "_id": "0009876543-26-000456",
                "_source": {
                    "accession_number": "0009876543-26-000456",
                    "entity_name": "Johnson & Johnson",
                    "entity_id": "200406",
                    "file_date": "2026-01-28",
                    "document_url": "https://www.sec.gov/Archives/edgar/data/200406/000987654326000456/jnj-10q.htm",
                    "description": "Quarterly Report",
                    "sic": "2834",
                },
            },
            {
                "_id": "0005555555-26-000789",
                "_source": {
                    "accession_number": "0005555555-26-000789",
                    "company_name": "Non-Pharma Corp",
                    "cik": "999999",
                    "filing_date": "2026-02-05",
                    "sic": "7372",  # Not pharma SIC
                },
            },
        ],
    },
}

SAMPLE_EDGAR_EMPTY = {
    "hits": {
        "hits": [],
    },
}


# ---------------------------------------------------------------------------
# Fetcher tests: initialization
# ---------------------------------------------------------------------------

class TestSECEdgarFetcherInit:
    """Tests for SEC EDGAR fetcher initialization."""

    def test_fetcher_init(self, tmp_path):
        """Verify fetcher initializes with correct source name."""
        fetcher = SECEdgarFetcher(data_dir=str(tmp_path))
        assert fetcher.SOURCE_NAME == "sec_edgar"
        assert fetcher.session is not None
        assert fetcher.data_dir == tmp_path

    def test_fetcher_user_agent_default(self, tmp_path):
        """Verify default User-Agent is set."""
        with patch.dict("os.environ", {}, clear=True):
            fetcher = SECEdgarFetcher(data_dir=str(tmp_path))
            assert fetcher.user_agent == DEFAULT_SEC_USER_AGENT
            assert fetcher.session.headers["User-Agent"] == DEFAULT_SEC_USER_AGENT

    def test_fetcher_user_agent_custom(self, tmp_path):
        """Verify custom User-Agent from env."""
        with patch.dict("os.environ", {
            "SEC_USER_AGENT": "MyCompany admin@mycompany.com"
        }):
            fetcher = SECEdgarFetcher(data_dir=str(tmp_path))
            assert fetcher.user_agent == "MyCompany admin@mycompany.com"

    def test_fetcher_accepts_json(self, tmp_path):
        """Verify Accept header is set to JSON."""
        fetcher = SECEdgarFetcher(data_dir=str(tmp_path))
        assert fetcher.session.headers.get("Accept") == "application/json"


# ---------------------------------------------------------------------------
# Fetcher tests: get_latest_url
# ---------------------------------------------------------------------------

class TestSECEdgarFetcherURL:
    """Tests for get_latest_url."""

    def test_get_latest_url(self, tmp_path):
        """Verify get_latest_url returns the EDGAR search API."""
        fetcher = SECEdgarFetcher(data_dir=str(tmp_path))
        url = fetcher.get_latest_url()
        assert "sec.gov" in url
        assert "search" in url


# ---------------------------------------------------------------------------
# Fetcher tests: fetch with mocked HTTP
# ---------------------------------------------------------------------------

class TestSECEdgarFetcherFetch:
    """Tests for the fetch method with mocked HTTP responses."""

    def test_fetch_success(self, tmp_path):
        """Test complete fetch with mocked EDGAR API."""
        fetcher = SECEdgarFetcher(data_dir=str(tmp_path))

        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_EDGAR_RESPONSE
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.session, "get", return_value=mock_response):
            result = fetcher.fetch(
                filing_types=["10-K"],
                days_back=30,
            )

        assert result["status"] == "success"
        assert result["hash"] is not None
        # Should have 2 records (non-pharma SIC filtered out)
        assert result["record_count"] == 2

        # Verify record structure
        rec = result["records"][0]
        assert rec["accession_number"] == "0001234567-26-000123"
        assert rec["company_name"] == "Pfizer Inc"
        assert rec["cik"] == "78003"
        assert rec["filing_type"] == "10-K"

    def test_fetch_empty_results(self, tmp_path):
        """Test fetch when no filings are found."""
        fetcher = SECEdgarFetcher(data_dir=str(tmp_path))

        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_EDGAR_EMPTY
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.session, "get", return_value=mock_response):
            result = fetcher.fetch(filing_types=["10-K"], days_back=1)

        assert result["status"] == "success"
        assert result["record_count"] == 0
        assert result["records"] == []

    def test_fetch_api_error(self, tmp_path):
        """Test fetch handles API errors gracefully."""
        fetcher = SECEdgarFetcher(data_dir=str(tmp_path))

        with patch.object(
            fetcher.session,
            "get",
            side_effect=Exception("Connection refused"),
        ):
            result = fetcher.fetch(filing_types=["10-K"])

        # Per-type search catches errors, overall succeeds with 0
        assert result["status"] == "success"
        assert result["record_count"] == 0

    def test_fetch_returns_failed_on_unexpected_error(self, tmp_path):
        """Test fetch returns failed on unexpected errors."""
        fetcher = SECEdgarFetcher(data_dir=str(tmp_path))

        with patch.object(
            fetcher,
            "_search_filings",
            side_effect=RuntimeError("Unexpected error"),
        ):
            result = fetcher.fetch(filing_types=["10-K"])

        assert result["status"] == "failed"
        assert "Unexpected error" in result["error"]

    def test_fetch_multiple_filing_types(self, tmp_path):
        """Test fetch across multiple filing types."""
        fetcher = SECEdgarFetcher(data_dir=str(tmp_path))

        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_EDGAR_RESPONSE
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher.session, "get", return_value=mock_response):
            result = fetcher.fetch(
                filing_types=["10-K", "10-Q", "8-K"],
                days_back=30,
            )

        assert result["status"] == "success"
        # Same accession numbers across types should be deduplicated
        assert result["record_count"] == 2


# ---------------------------------------------------------------------------
# Fetcher tests: SIC filtering
# ---------------------------------------------------------------------------

class TestSICFiltering:
    """Tests for pharmaceutical SIC code filtering."""

    def test_pharma_sic_included(self):
        """Records with pharma SIC codes are included."""
        record = {"accession_number": "001", "_sic": "2834"}
        assert SECEdgarFetcher._is_pharma_company(record, PHARMA_SIC_CODES) is True

    def test_non_pharma_sic_excluded(self):
        """Records with non-pharma SIC codes are excluded."""
        record = {"accession_number": "001", "_sic": "7372"}
        assert SECEdgarFetcher._is_pharma_company(record, PHARMA_SIC_CODES) is False

    def test_missing_sic_included(self):
        """Records without SIC code are included (cannot filter)."""
        record = {"accession_number": "001"}
        assert SECEdgarFetcher._is_pharma_company(record, PHARMA_SIC_CODES) is True


# ---------------------------------------------------------------------------
# Fetcher tests: normalization
# ---------------------------------------------------------------------------

class TestSECEdgarNormalization:
    """Tests for filing record normalization."""

    def test_normalize_filing_full(self, tmp_path):
        """Full filing record normalizes correctly."""
        fetcher = SECEdgarFetcher(data_dir=str(tmp_path))

        hit = {
            "_id": "001-26-000123",
            "_source": {
                "accession_number": "001-26-000123",
                "company_name": "TestPharma",
                "cik": "12345",
                "filing_date": "2026-02-01",
                "file_url": "https://sec.gov/test",
                "file_description": "Annual Report",
                "sic": "2834",
            },
        }

        result = fetcher._normalize_filing(hit, "10-K")

        assert result["accession_number"] == "001-26-000123"
        assert result["company_name"] == "TestPharma"
        assert result["cik"] == "12345"
        assert result["filing_type"] == "10-K"
        assert result["filing_date"] == "2026-02-01"

    def test_normalize_filing_no_id(self, tmp_path):
        """Filing without accession number returns None."""
        fetcher = SECEdgarFetcher(data_dir=str(tmp_path))
        result = fetcher._normalize_filing({"_source": {}}, "10-K")
        assert result is None


# ---------------------------------------------------------------------------
# Validator tests: valid records
# ---------------------------------------------------------------------------

class TestSECEdgarRecordValid:
    """Tests for valid SECEdgarRecord instances."""

    def test_full_record(self):
        """Fully populated record validates successfully."""
        record = SECEdgarRecord(
            accession_number="0001234567-26-000123",
            company_name="Pfizer Inc",
            cik="78003",
            filing_type="10-K",
            filing_date=date(2026, 2, 1),
            document_url="https://www.sec.gov/test",
            description="Annual Report",
        )
        assert record.accession_number == "0001234567-26-000123"
        assert record.filing_type == "10-K"
        assert record.cik == "78003"

    def test_minimal_record(self):
        """Minimal record with only required fields."""
        record = SECEdgarRecord(
            accession_number="0001234567-26-000456",
            filing_type="10-Q",
        )
        assert record.accession_number == "0001234567-26-000456"
        assert record.filing_type == "10-Q"
        assert record.company_name is None
        assert record.cik is None

    def test_all_valid_filing_types(self):
        """Every valid filing type is accepted."""
        for ft in ["10-K", "10-Q", "8-K"]:
            record = SECEdgarRecord(
                accession_number=f"ACC-{ft}",
                filing_type=ft,
            )
            assert record.filing_type == ft


# ---------------------------------------------------------------------------
# Validator tests: invalid records
# ---------------------------------------------------------------------------

class TestSECEdgarRecordInvalid:
    """Tests for invalid SECEdgarRecord instances."""

    def test_empty_accession_number(self):
        """Empty accession_number is rejected."""
        with pytest.raises(Exception):
            SECEdgarRecord(accession_number="", filing_type="10-K")

    def test_missing_accession_number(self):
        """Missing accession_number is rejected."""
        with pytest.raises(Exception):
            SECEdgarRecord(filing_type="10-K")

    def test_invalid_filing_type(self):
        """Invalid filing_type is rejected."""
        with pytest.raises(Exception) as exc_info:
            SECEdgarRecord(
                accession_number="001-26-000123",
                filing_type="INVALID",
            )
        assert "filing_type" in str(exc_info.value).lower() or "INVALID" in str(exc_info.value)

    def test_missing_filing_type(self):
        """Missing filing_type is rejected."""
        with pytest.raises(Exception):
            SECEdgarRecord(accession_number="001-26-000123")

    def test_non_numeric_cik(self):
        """Non-numeric CIK is rejected."""
        with pytest.raises(Exception) as exc_info:
            SECEdgarRecord(
                accession_number="001-26-000123",
                filing_type="10-K",
                cik="ABC",
            )
        assert "CIK" in str(exc_info.value) or "numeric" in str(exc_info.value).lower()
