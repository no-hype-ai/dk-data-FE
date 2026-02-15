"""Tests for ORCID fetcher with mocked HTTP.

Feature: 012-platform-hardening (US3)
"""

import tempfile

import pytest
import responses

from dk_data.ingestion.fetchers.orcid import ORCIDFetcher
from dk_data.ingestion.utils.validators import ORCIDRecord


ORCID_SEARCH_RESPONSE = {
    "result": [
        {"orcid-identifier": {"path": "0000-0002-1825-0097"}},
        {"orcid-identifier": {"path": "0000-0001-5109-3700"}},
    ]
}

ORCID_PROFILE_RESPONSE = {
    "person": {
        "name": {
            "given-names": {"value": "Jane"},
            "family-name": {"value": "Doe"},
            "credit-name": {"value": "Jane M. Doe"},
        },
        "biography": {"content": "Pharmaceutical researcher."},
        "keywords": {
            "keyword": [
                {"content": "drug discovery"},
                {"content": "oncology"},
            ]
        },
        "external-identifiers": {
            "external-identifier": [
                {"external-id-type": "Scopus Author ID", "external-id-value": "12345678"},
            ]
        },
    },
    "activities-summary": {
        "employments": {
            "affiliation-group": [
                {
                    "summaries": [
                        {
                            "employment-summary": {
                                "organization": {"name": "MIT"},
                                "role-title": "Professor",
                                "department-name": "Chemistry",
                            }
                        }
                    ]
                }
            ]
        },
        "works": {"group": [{"work-summary": [{}]}, {"work-summary": [{}]}]},
    },
}

ORCID_EMPTY_SEARCH = {"result": []}


class TestORCIDFetcher:
    """Tests for ORCIDFetcher."""

    def test_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = ORCIDFetcher(data_dir=tmpdir)
            assert fetcher.SOURCE_NAME == "orcid"
            assert "pub.orcid.org" in fetcher.BASE_URL

    def test_get_latest_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = ORCIDFetcher(data_dir=tmpdir)
            assert "search" in fetcher.get_latest_url()

    @responses.activate
    def test_fetch_success(self):
        # Mock search
        responses.add(
            responses.GET,
            "https://pub.orcid.org/v3.0/search",
            json=ORCID_SEARCH_RESPONSE,
            status=200,
        )
        # Mock profile for first ORCID
        responses.add(
            responses.GET,
            "https://pub.orcid.org/v3.0/0000-0002-1825-0097/record",
            json=ORCID_PROFILE_RESPONSE,
            status=200,
        )
        # Mock profile for second ORCID
        responses.add(
            responses.GET,
            "https://pub.orcid.org/v3.0/0000-0001-5109-3700/record",
            json=ORCID_PROFILE_RESPONSE,
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = ORCIDFetcher(data_dir=tmpdir)
            result = fetcher.fetch()

        assert result["status"] == "success"
        assert len(result["records"]) == 2
        assert result["records"][0]["orcid_id"] == "0000-0002-1825-0097"
        assert result["records"][0]["given_names"] == "Jane"
        assert result["records"][0]["family_name"] == "Doe"
        assert "drug discovery" in result["records"][0]["keywords"]
        assert result["records"][0]["current_affiliations"][0]["organization"] == "MIT"

    @responses.activate
    def test_fetch_empty(self):
        responses.add(
            responses.GET,
            "https://pub.orcid.org/v3.0/search",
            json=ORCID_EMPTY_SEARCH,
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = ORCIDFetcher(data_dir=tmpdir)
            result = fetcher.fetch()

        assert result["status"] == "success"
        assert len(result["records"]) == 0

    @responses.activate
    def test_fetch_http_error(self):
        responses.add(
            responses.GET,
            "https://pub.orcid.org/v3.0/search",
            body=b"Service Unavailable",
            status=503,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = ORCIDFetcher(data_dir=tmpdir)
            result = fetcher.fetch()

        assert result["status"] == "failed"
        assert result["error"]


class TestORCIDRecord:
    """Tests for ORCIDRecord validator."""

    def test_valid_record(self):
        record = ORCIDRecord(
            orcid_id="0000-0002-1825-0097",
            given_names="Jane",
            family_name="Doe",
            credit_name="Jane M. Doe",
        )
        assert record.orcid_id == "0000-0002-1825-0097"

    def test_minimal_record(self):
        record = ORCIDRecord(orcid_id="0000-0002-1825-0097")
        assert record.given_names is None

    def test_invalid_orcid_format(self):
        with pytest.raises(ValueError):
            ORCIDRecord(orcid_id="invalid-format")

    def test_orcid_whitespace_stripped(self):
        record = ORCIDRecord(orcid_id="  0000-0002-1825-0097  ")
        assert record.orcid_id == "0000-0002-1825-0097"
