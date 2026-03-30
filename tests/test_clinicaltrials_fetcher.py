"""Tests for ClinicalTrials.gov v2 fetcher with mocked HTTP.

Feature: 019-cms-puf-platform-reconciliation

Tests use mocked HTTP responses -- no external network calls are made.
Verifies:
- Successful fetch with token-based pagination (2 pages)
- Empty results (no studies returned)
- max_records cap honored
- HTTP error handling (500 response)
- Date scoping parameter construction
"""

import json
import tempfile
from unittest.mock import patch

import responses

from dk_data.ingestion.fetchers.clinicaltrials import (
    BASE_URL,
    ClinicalTrialsFetcher,
    PAGE_SIZE,
)


def _make_fetcher():
    tmpdir = tempfile.mkdtemp()
    return ClinicalTrialsFetcher(data_dir=tmpdir)


def _study(nct_id: str) -> dict:
    """Return a minimal study dict matching ClinicalTrials.gov v2 shape."""
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct_id},
            "statusModule": {"overallStatus": "Recruiting"},
        }
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestClinicalTrialsFetcherSuccess:
    """Happy-path: two pages of studies, second page has no nextPageToken."""

    @responses.activate
    def test_fetch_two_pages(self):
        page1_studies = [_study(f"NCT0000000{i}") for i in range(3)]
        page2_studies = [_study(f"NCT0000001{i}") for i in range(2)]

        responses.add(
            responses.GET,
            BASE_URL,
            json={"studies": page1_studies, "nextPageToken": "tok_page2"},
            status=200,
        )
        responses.add(
            responses.GET,
            BASE_URL,
            json={"studies": page2_studies},  # no nextPageToken => last page
            status=200,
        )

        fetcher = _make_fetcher()
        result = fetcher.fetch(days_back=7, max_records=10_000)

        assert result["status"] == "success"
        # Two page blobs
        assert result["record_count"] == 2
        assert len(result["records"]) == 2
        assert result["_total_studies"] == 5
        assert result["hash"] is not None

        # Each page blob has expected keys
        for blob in result["records"]:
            assert "studies" in blob
            assert "_request_id" in blob
            assert "_page_number" in blob

    @responses.activate
    def test_page_blobs_contain_studies(self):
        studies = [_study("NCT11111111")]
        responses.add(
            responses.GET,
            BASE_URL,
            json={"studies": studies},
            status=200,
        )

        fetcher = _make_fetcher()
        result = fetcher.fetch(days_back=30)

        blob = result["records"][0]
        assert blob["studies"] == studies
        assert blob["_page_number"] == 0


class TestClinicalTrialsFetcherEmpty:
    """API returns no studies."""

    @responses.activate
    def test_empty_results(self):
        responses.add(
            responses.GET,
            BASE_URL,
            json={"studies": []},
            status=200,
        )

        fetcher = _make_fetcher()
        result = fetcher.fetch(days_back=7)

        assert result["status"] == "success"
        assert result["records"] == []
        assert result["record_count"] == 0
        assert result["_total_studies"] == 0


class TestClinicalTrialsFetcherMaxRecords:
    """max_records cap stops pagination early."""

    @responses.activate
    def test_max_records_cap(self):
        # max_records=3, first page returns 3 studies with a next token,
        # but fetcher should stop because it already hit the cap.
        studies = [_study(f"NCT9999000{i}") for i in range(3)]
        responses.add(
            responses.GET,
            BASE_URL,
            json={"studies": studies, "nextPageToken": "more"},
            status=200,
        )
        # Second page should NOT be requested
        responses.add(
            responses.GET,
            BASE_URL,
            json={"studies": [_study("NCT99990099")]},
            status=200,
        )

        fetcher = _make_fetcher()
        result = fetcher.fetch(max_records=3)

        assert result["status"] == "success"
        assert result["_total_studies"] == 3
        # Only one page fetched
        assert result["record_count"] == 1
        # Verify only the first responses call was used (1 call total)
        assert len(responses.calls) == 1


class TestClinicalTrialsFetcherHTTPError:
    """HTTP errors are handled gracefully."""

    @responses.activate
    def test_http_500_on_first_page_returns_empty_success(self):
        """A 500 on the first page is caught inside _paginate; fetch returns
        success with zero records (pagination breaks but no top-level exception)."""
        responses.add(
            responses.GET,
            BASE_URL,
            json={"error": "Internal Server Error"},
            status=500,
        )

        fetcher = _make_fetcher()
        result = fetcher.fetch(days_back=7)

        # _paginate catches the page-level exception and breaks
        assert result["status"] == "success"
        assert result["records"] == []
        assert result["record_count"] == 0
        assert result["_total_studies"] == 0

    def test_network_error_degrades_gracefully(self):
        """A connection error on the first page is caught inside _paginate and
        results in an empty success (pagination breaks, no studies collected)."""
        from requests.exceptions import ConnectionError as ReqConnError

        fetcher = _make_fetcher()
        with patch.object(fetcher.session, "get", side_effect=ReqConnError("DNS failure")):
            result = fetcher.fetch(days_back=7)

        # _paginate swallows per-page exceptions and breaks
        assert result["status"] == "success"
        assert result["records"] == []
        assert result["_total_studies"] == 0

    def test_unexpected_error_in_fetch_returns_failed(self):
        """An error raised outside _paginate (e.g. in date computation)
        triggers the top-level exception handler and returns status='failed'."""
        fetcher = _make_fetcher()
        with patch.object(fetcher, "_paginate", side_effect=RuntimeError("boom")):
            result = fetcher.fetch(days_back=7)

        assert result["status"] == "failed"
        assert "error" in result
        assert result["records"] == []


class TestClinicalTrialsFetcherDateScoping:
    """Verify the filter.advanced date range parameter is constructed correctly."""

    @responses.activate
    def test_date_filter_includes_range(self):
        responses.add(
            responses.GET,
            BASE_URL,
            json={"studies": []},
            status=200,
        )

        fetcher = _make_fetcher()
        fetcher.fetch(days_back=30)

        # Inspect the actual request params
        assert len(responses.calls) == 1
        request_url = responses.calls[0].request.url

        # Must include the LastUpdatePostDate RANGE filter
        assert "AREA%5BLastUpdatePostDate%5DRANGE" in request_url or \
               "AREA[LastUpdatePostDate]RANGE" in request_url

        # The range should end with ,MAX]
        assert "MAX" in request_url

    @responses.activate
    def test_condition_and_intervention_params(self):
        """Optional condition/intervention kwargs appear in the request."""
        responses.add(
            responses.GET,
            BASE_URL,
            json={"studies": []},
            status=200,
        )

        fetcher = _make_fetcher()
        fetcher.fetch(condition="cancer", intervention="pembrolizumab")

        request_url = responses.calls[0].request.url
        assert "cancer" in request_url
        assert "pembrolizumab" in request_url
