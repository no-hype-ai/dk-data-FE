"""Tests for ClinicalTrials.gov v2 fetcher with mocked HTTP.

Feature: 019-cms-puf-platform-reconciliation

Tests use mocked HTTP responses -- no external network calls are made.
Verifies:
- Successful fetch with token-based pagination (2 pages)
- Empty results (no studies returned)
- max_records cap honored
- HTTP error handling (500 response)
- Date scoping parameter construction

Note: The fetcher is self-loading (streams directly to DB). Tests mock
load_clinicaltrials_data so no DB connection is required.
"""

import tempfile
from unittest.mock import MagicMock, patch

import responses

from dk_data.ingestion.fetchers.clinicaltrials import (
    BASE_URL,
    ClinicalTrialsFetcher,
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
    @patch("dk_data.ingestion.fetchers.clinicaltrials.load_clinicaltrials_data")
    @patch("dk_data.ingestion.fetchers.clinicaltrials.load_checkpoint", return_value=None)
    @patch("dk_data.ingestion.fetchers.clinicaltrials.save_checkpoint")
    @patch("dk_data.ingestion.fetchers.clinicaltrials.clear_checkpoint")
    def test_fetch_two_pages(self, mock_clear, mock_save, mock_load_cp, mock_loader):
        mock_loader.return_value = {"records_inserted": 5, "records_failed": 0}

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
        # Self-loading: records are streamed to DB, not returned
        assert result["records"] == []
        assert result["_total_studies"] == 5
        assert result["hash"] is not None
        # Two pages were processed
        assert result["record_count"] == 2

    @responses.activate
    @patch("dk_data.ingestion.fetchers.clinicaltrials.load_clinicaltrials_data")
    @patch("dk_data.ingestion.fetchers.clinicaltrials.load_checkpoint", return_value=None)
    @patch("dk_data.ingestion.fetchers.clinicaltrials.save_checkpoint")
    @patch("dk_data.ingestion.fetchers.clinicaltrials.clear_checkpoint")
    def test_page_blobs_contain_studies(self, mock_clear, mock_save, mock_load_cp, mock_loader):
        """Verify the loader is called with blobs that contain the studies array."""
        mock_loader.return_value = {"records_inserted": 1, "records_failed": 0}
        studies = [_study("NCT11111111")]
        responses.add(
            responses.GET,
            BASE_URL,
            json={"studies": studies},
            status=200,
        )

        fetcher = _make_fetcher()
        result = fetcher.fetch(days_back=30)

        assert result["status"] == "success"
        # Loader should have been called with a list containing one page blob
        assert mock_loader.called
        call_args = mock_loader.call_args[0][0]  # first positional arg = records list
        assert len(call_args) == 1
        blob = call_args[0]
        assert blob["studies"] == studies
        assert blob["_page_number"] == 0


class TestClinicalTrialsFetcherEmpty:
    """API returns no studies."""

    @responses.activate
    @patch("dk_data.ingestion.fetchers.clinicaltrials.load_checkpoint", return_value=None)
    @patch("dk_data.ingestion.fetchers.clinicaltrials.clear_checkpoint")
    def test_empty_results(self, mock_clear, mock_load_cp):
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
    @patch("dk_data.ingestion.fetchers.clinicaltrials.load_clinicaltrials_data")
    @patch("dk_data.ingestion.fetchers.clinicaltrials.load_checkpoint", return_value=None)
    @patch("dk_data.ingestion.fetchers.clinicaltrials.save_checkpoint")
    @patch("dk_data.ingestion.fetchers.clinicaltrials.clear_checkpoint")
    def test_max_records_cap(self, mock_clear, mock_save, mock_load_cp, mock_loader):
        mock_loader.return_value = {"records_inserted": 3, "records_failed": 0}

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
        # Verify only the first responses call was used (1 call total)
        assert len(responses.calls) == 1


class TestClinicalTrialsFetcherHTTPError:
    """HTTP errors are handled gracefully."""

    @responses.activate
    @patch("dk_data.ingestion.fetchers.clinicaltrials.load_checkpoint", return_value=None)
    @patch("dk_data.ingestion.fetchers.clinicaltrials.save_checkpoint")
    def test_http_500_on_first_page_returns_failed(self, mock_save, mock_load_cp):
        """A 500 on the first page raises, which the top-level handler catches
        and returns status='failed'. This is the correct behavior: a network
        failure should not silently report success with zero records."""
        responses.add(
            responses.GET,
            BASE_URL,
            json={"error": "Internal Server Error"},
            status=500,
        )

        fetcher = _make_fetcher()
        result = fetcher.fetch(days_back=7)

        assert result["status"] == "failed"
        assert result["records"] == []
        assert result["record_count"] == 0

    def test_network_error_returns_failed(self):
        """A connection error raises, which the top-level handler catches and
        returns status='failed'. Partial progress is checkpointed before raising."""
        from requests.exceptions import ConnectionError as ReqConnError

        fetcher = _make_fetcher()
        with patch("dk_data.ingestion.fetchers.clinicaltrials.load_checkpoint", return_value=None), \
             patch("dk_data.ingestion.fetchers.clinicaltrials.save_checkpoint"), \
             patch.object(fetcher.session, "get", side_effect=ReqConnError("DNS failure")):
            result = fetcher.fetch(days_back=7)

        assert result["status"] == "failed"
        assert result["records"] == []

    def test_unexpected_error_in_fetch_returns_failed(self):
        """An error raised inside _fetch_and_load triggers the top-level
        exception handler and returns status='failed'."""
        fetcher = _make_fetcher()
        with patch.object(fetcher, "_fetch_and_load", side_effect=RuntimeError("boom")):
            result = fetcher.fetch(days_back=7)

        assert result["status"] == "failed"
        assert "error" in result
        assert result["records"] == []


class TestClinicalTrialsFetcherDateScoping:
    """Verify the filter.advanced date range parameter is constructed correctly."""

    @responses.activate
    @patch("dk_data.ingestion.fetchers.clinicaltrials.load_checkpoint", return_value=None)
    @patch("dk_data.ingestion.fetchers.clinicaltrials.clear_checkpoint")
    def test_date_filter_includes_range(self, mock_clear, mock_load_cp):
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
    @patch("dk_data.ingestion.fetchers.clinicaltrials.load_checkpoint", return_value=None)
    @patch("dk_data.ingestion.fetchers.clinicaltrials.clear_checkpoint")
    def test_condition_and_intervention_params(self, mock_clear, mock_load_cp):
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
