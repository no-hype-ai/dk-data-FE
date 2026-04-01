"""Tests for EPO OPS Fetcher and EPOPatentRecord validator.

Feature: 011-datasource-integration
Task: T061-T063 — EPO OPS patent data

Tests cover:
- Fetcher initialization and session configuration
- get_latest_url endpoint
- OAuth2 token acquisition
- Full fetch with mocked OPS API (XML responses)
- EPOPatentRecord validation (valid and invalid)
- Date parsing helper
"""

import textwrap
from datetime import date
from unittest.mock import patch

import pytest
import responses

from dk_data.ingestion.fetchers.epo_ops import EPOOPSFetcher
from dk_data.ingestion.utils.validators import EPOPatentRecord


# ---------------------------------------------------------------------------
# Sample OPS API XML response fixtures
# ---------------------------------------------------------------------------

SAMPLE_OPS_SEARCH_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <ops:world-patent-data xmlns:ops="http://ops.epo.org"
        xmlns:epo="http://www.epo.org/exchange"
        xmlns:xlink="http://www.w3.org/1999/xlink">
        <ops:biblio-search>
            <ops:search-result>
                <ops:publication-reference>
                    <epo:document-id>
                        <epo:country>EP</epo:country>
                        <epo:doc-number>3456789</epo:doc-number>
                        <epo:kind>A1</epo:kind>
                    </epo:document-id>
                </ops:publication-reference>
                <epo:exchange-document country="EP" doc-number="3456789" kind="A1" family-id="F12345">
                    <epo:bibliographic-data>
                        <epo:invention-title lang="en">Novel Pharmaceutical Composition</epo:invention-title>
                        <epo:parties>
                            <epo:applicants>
                                <epo:applicant>
                                    <epo:applicant-name>
                                        <epo:name>Pharma Corp</epo:name>
                                    </epo:applicant-name>
                                </epo:applicant>
                            </epo:applicants>
                            <epo:inventors>
                                <epo:inventor>
                                    <epo:inventor-name>
                                        <epo:name>Smith, John</epo:name>
                                    </epo:inventor-name>
                                </epo:inventor>
                            </epo:inventors>
                        </epo:parties>
                        <epo:application-reference>
                            <epo:document-id>
                                <epo:date>20240115</epo:date>
                            </epo:document-id>
                        </epo:application-reference>
                        <epo:publication-reference>
                            <epo:document-id>
                                <epo:date>20240715</epo:date>
                            </epo:document-id>
                        </epo:publication-reference>
                    </epo:bibliographic-data>
                    <epo:abstract lang="en">
                        <epo:p>A pharmaceutical composition for treating cancer.</epo:p>
                    </epo:abstract>
                </epo:exchange-document>
            </ops:search-result>
        </ops:biblio-search>
    </ops:world-patent-data>
""")

SAMPLE_OPS_EMPTY_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <ops:world-patent-data xmlns:ops="http://ops.epo.org"
        xmlns:epo="http://www.epo.org/exchange">
        <ops:biblio-search>
            <ops:search-result/>
        </ops:biblio-search>
    </ops:world-patent-data>
""")

TOKEN_RESPONSE = {
    "access_token": "test_token_abc123",
    "token_type": "Bearer",
    "expires_in": 1200,
}


# ---------------------------------------------------------------------------
# Fetcher tests: initialization
# ---------------------------------------------------------------------------

class TestEPOOPSFetcherInit:
    """Tests for EPO OPS fetcher initialization."""

    def test_fetcher_init(self, tmp_path):
        """Verify fetcher initializes with correct source name and URLs."""
        fetcher = EPOOPSFetcher(data_dir=str(tmp_path))
        assert fetcher.SOURCE_NAME == "epo_ops"
        assert "ops.epo.org" in fetcher.BASE_URL
        assert fetcher.session is not None
        assert fetcher.data_dir == tmp_path

    def test_fetcher_init_with_credentials(self, tmp_path):
        """Verify fetcher reads EPO credentials from environment."""
        with patch.dict("os.environ", {
            "EPO_CONSUMER_KEY": "test_key",
            "EPO_CONSUMER_SECRET": "test_secret",
        }):
            fetcher = EPOOPSFetcher(data_dir=str(tmp_path))
            assert fetcher.consumer_key == "test_key"
            assert fetcher.consumer_secret == "test_secret"

    def test_fetcher_init_without_credentials(self, tmp_path):
        """Verify fetcher handles missing credentials gracefully."""
        with patch.dict("os.environ", {}, clear=True):
            fetcher = EPOOPSFetcher(data_dir=str(tmp_path))
            assert fetcher.consumer_key is None
            assert fetcher.consumer_secret is None


# ---------------------------------------------------------------------------
# Fetcher tests: get_latest_url
# ---------------------------------------------------------------------------

class TestEPOOPSFetcherURL:
    """Tests for get_latest_url."""

    def test_get_latest_url(self, tmp_path):
        """Verify get_latest_url returns the OPS search endpoint."""
        fetcher = EPOOPSFetcher(data_dir=str(tmp_path))
        url = fetcher.get_latest_url()
        assert "ops.epo.org" in url
        assert "published-data/search" in url


# ---------------------------------------------------------------------------
# Fetcher tests: OAuth2 token
# ---------------------------------------------------------------------------

class TestEPOOPSToken:
    """Tests for OAuth2 token acquisition."""

    @responses.activate
    def test_ensure_token(self, tmp_path):
        """Verify OAuth2 token is obtained successfully."""
        responses.add(
            responses.POST,
            "https://ops.epo.org/3.2/auth/accesstoken",
            json=TOKEN_RESPONSE,
            status=200,
        )

        with patch.dict("os.environ", {
            "EPO_CONSUMER_KEY": "test_key",
            "EPO_CONSUMER_SECRET": "test_secret",
        }):
            fetcher = EPOOPSFetcher(data_dir=str(tmp_path))
            fetcher._ensure_token()

            assert fetcher._access_token == "test_token_abc123"
            assert fetcher._token_expires_at > 0

    def test_ensure_token_missing_credentials(self, tmp_path):
        """Verify token request fails without credentials."""
        with patch.dict("os.environ", {}, clear=True):
            fetcher = EPOOPSFetcher(data_dir=str(tmp_path))

            with pytest.raises(RuntimeError, match="EPO_CONSUMER_KEY"):
                fetcher._ensure_token()


# ---------------------------------------------------------------------------
# Fetcher tests: fetch with mocked HTTP
# ---------------------------------------------------------------------------

class TestEPOOPSFetcherFetch:
    """Tests for the fetch method with mocked HTTP responses."""

    @responses.activate
    def test_fetch_success(self, tmp_path):
        """Test a complete fetch with mocked OPS API."""
        # Mock OAuth token
        responses.add(
            responses.POST,
            "https://ops.epo.org/3.2/auth/accesstoken",
            json=TOKEN_RESPONSE,
            status=200,
        )
        # Mock search results
        responses.add(
            responses.GET,
            "https://ops.epo.org/3.2/rest-services/published-data/search/biblio",
            body=SAMPLE_OPS_SEARCH_XML.encode(),
            status=200,
            content_type="application/xml",
        )
        # Mock empty second page (no more results)
        responses.add(
            responses.GET,
            "https://ops.epo.org/3.2/rest-services/published-data/search/biblio",
            status=404,
        )

        with patch.dict("os.environ", {
            "EPO_CONSUMER_KEY": "test_key",
            "EPO_CONSUMER_SECRET": "test_secret",
        }):
            fetcher = EPOOPSFetcher(data_dir=str(tmp_path))
            result = fetcher.fetch(
                search_terms=["cancer treatment"],
                days_back=30,
            )

        assert result["status"] == "success"
        assert result["record_count"] >= 1
        assert result["hash"] is not None
        assert len(result["records"]) >= 1

        rec = result["records"][0]
        assert "publication_id" in rec
        assert rec["publication_id"] == "EP3456789A1"

    @responses.activate
    def test_fetch_empty_results(self, tmp_path):
        """Test fetch when no patents are found."""
        responses.add(
            responses.POST,
            "https://ops.epo.org/3.2/auth/accesstoken",
            json=TOKEN_RESPONSE,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://ops.epo.org/3.2/rest-services/published-data/search/biblio",
            body=SAMPLE_OPS_EMPTY_XML.encode(),
            status=200,
            content_type="application/xml",
        )

        with patch.dict("os.environ", {
            "EPO_CONSUMER_KEY": "test_key",
            "EPO_CONSUMER_SECRET": "test_secret",
        }):
            fetcher = EPOOPSFetcher(data_dir=str(tmp_path))
            result = fetcher.fetch(search_terms=["nonexistent_drug_xyz"])

        assert result["status"] == "success"
        assert result["record_count"] == 0
        assert result["records"] == []

    def test_fetch_no_credentials(self, tmp_path):
        """Test fetch degrades gracefully without credentials.

        EPO OPS returns source_unavailable (not failed) when credentials are
        missing — deliberate distinction: it is not a transient error but a
        known configuration gap that does not warrant a failure alert.
        """
        with patch.dict("os.environ", {}, clear=True):
            fetcher = EPOOPSFetcher(data_dir=str(tmp_path))
            result = fetcher.fetch(search_terms=["test"])

        assert result["status"] == "source_unavailable"
        assert "error" in result

    @responses.activate
    def test_fetch_api_error(self, tmp_path):
        """Test fetch handles API errors gracefully."""
        responses.add(
            responses.POST,
            "https://ops.epo.org/3.2/auth/accesstoken",
            json=TOKEN_RESPONSE,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://ops.epo.org/3.2/rest-services/published-data/search/biblio",
            json={"error": "service unavailable"},
            status=500,
        )

        with patch.dict("os.environ", {
            "EPO_CONSUMER_KEY": "test_key",
            "EPO_CONSUMER_SECRET": "test_secret",
        }):
            fetcher = EPOOPSFetcher(data_dir=str(tmp_path))
            result = fetcher.fetch(search_terms=["test"])

        # Should succeed with 0 records since per-term search catches errors
        assert result["status"] == "success"
        assert result["record_count"] == 0


# ---------------------------------------------------------------------------
# Fetcher tests: date parsing
# ---------------------------------------------------------------------------

class TestEPODateParsing:
    """Tests for EPO date format parsing."""

    def test_parse_date_standard(self):
        """Standard YYYYMMDD format."""
        assert EPOOPSFetcher._parse_date("20240115") == "2024-01-15"

    def test_parse_date_empty(self):
        """Empty string returns None."""
        assert EPOOPSFetcher._parse_date("") is None

    def test_parse_date_none(self):
        """None returns None."""
        assert EPOOPSFetcher._parse_date(None) is None

    def test_parse_date_short(self):
        """Short string returns None."""
        assert EPOOPSFetcher._parse_date("2024") is None


# ---------------------------------------------------------------------------
# Validator tests: valid records
# ---------------------------------------------------------------------------

class TestEPOPatentRecordValid:
    """Tests for valid EPOPatentRecord instances."""

    def test_full_record(self):
        """Fully populated record validates successfully."""
        record = EPOPatentRecord(
            publication_id="EP3456789A1",
            title="Novel Pharmaceutical Composition",
            abstract="A composition for treating cancer.",
            applicants=["Pharma Corp"],
            inventors=["Smith, John"],
            filing_date=date(2024, 1, 15),
            publication_date=date(2024, 7, 15),
            ipc_codes=["A61K31/00", "A61P35/00"],
            family_id="F12345",
        )
        assert record.publication_id == "EP3456789A1"
        assert record.title == "Novel Pharmaceutical Composition"
        assert record.ipc_codes == ["A61K31/00", "A61P35/00"]
        assert record.applicants == ["Pharma Corp"]

    def test_minimal_record(self):
        """Minimal record with only required fields."""
        record = EPOPatentRecord(publication_id="US20240001A1")
        assert record.publication_id == "US20240001A1"
        assert record.title is None
        assert record.abstract is None
        assert record.applicants is None
        assert record.ipc_codes is None

    def test_record_with_none_optionals(self):
        """Record with explicit None values for optional fields."""
        record = EPOPatentRecord(
            publication_id="WO2024000001A1",
            title=None,
            filing_date=None,
            family_id=None,
        )
        assert record.publication_id == "WO2024000001A1"


# ---------------------------------------------------------------------------
# Validator tests: invalid records
# ---------------------------------------------------------------------------

class TestEPOPatentRecordInvalid:
    """Tests for invalid EPOPatentRecord instances."""

    def test_empty_publication_id(self):
        """Empty publication_id is rejected."""
        with pytest.raises(Exception):
            EPOPatentRecord(publication_id="")

    def test_missing_publication_id(self):
        """Missing publication_id is rejected."""
        with pytest.raises(Exception):
            EPOPatentRecord()

    def test_whitespace_only_publication_id(self):
        """Whitespace-only publication_id is rejected."""
        with pytest.raises(Exception):
            EPOPatentRecord(publication_id="   ")
