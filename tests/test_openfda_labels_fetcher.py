"""Tests for OpenFDA Labels fetcher with mocked HTTP.

Feature: 019-cms-puf-platform-reconciliation

Tests use mocked HTTP responses -- no external network calls are made.
Verifies:
- Successful fetch with skip/limit pagination (2 pages)
- 25k per-query limit is enforced
- Empty results
- HTTP error handling
- Date scoping parameter construction
"""

import tempfile
from unittest.mock import patch

import responses

from dk_data.ingestion.fetchers.openfda_labels import (
    BASE_URL,
    FDA_SKIP_LIMIT,
    OpenFDALabelsFetcher,
    PAGE_SIZE,
)


def _make_fetcher():
    tmpdir = tempfile.mkdtemp()
    return OpenFDALabelsFetcher(data_dir=tmpdir)


def _label(spl_id: str) -> dict:
    """Return a minimal drug label record matching openFDA shape."""
    return {
        "spl_id": spl_id,
        "openfda": {"brand_name": [f"Drug-{spl_id}"]},
        "effective_time": "20260101",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOpenFDALabelsFetcherSuccess:
    """Happy-path: two pages of labels."""

    @responses.activate
    def test_fetch_two_pages(self):
        page1_results = [_label(f"SPL-{i:04d}") for i in range(100)]
        page2_results = [_label(f"SPL-{i:04d}") for i in range(100, 150)]

        responses.add(
            responses.GET,
            BASE_URL,
            json={"results": page1_results, "meta": {"results": {"total": 150}}},
            status=200,
        )
        responses.add(
            responses.GET,
            BASE_URL,
            json={"results": page2_results, "meta": {"results": {"total": 150}}},
            status=200,
        )

        fetcher = _make_fetcher()
        result = fetcher.fetch(days_back=90, max_records=5000)

        assert result["status"] == "success"
        assert result["record_count"] == 2
        assert len(result["records"]) == 2
        assert result["_total_labels"] == 150
        assert result["hash"] is not None

        # Each page blob has expected keys
        for blob in result["records"]:
            assert "results" in blob
            assert "_request_id" in blob
            assert "_page_number" in blob

    @responses.activate
    def test_page_blobs_contain_results(self):
        labels = [_label("SPL-SINGLE")]
        responses.add(
            responses.GET,
            BASE_URL,
            json={"results": labels},
            status=200,
        )

        fetcher = _make_fetcher()
        result = fetcher.fetch(days_back=90)

        blob = result["records"][0]
        assert blob["results"] == labels
        assert blob["_page_number"] == 0

    @responses.activate
    def test_skip_limit_pagination_params(self):
        """Verify skip/limit params increment correctly across pages."""
        page1 = [_label(f"SPL-{i}") for i in range(100)]
        page2 = [_label(f"SPL-{i}") for i in range(100, 130)]

        responses.add(responses.GET, BASE_URL, json={"results": page1}, status=200)
        responses.add(responses.GET, BASE_URL, json={"results": page2}, status=200)

        fetcher = _make_fetcher()
        fetcher.fetch(days_back=90, max_records=5000)

        # First request: skip=0
        url0 = responses.calls[0].request.url
        assert "skip=0" in url0
        assert "limit=100" in url0

        # Second request: skip=100
        url1 = responses.calls[1].request.url
        assert "skip=100" in url1


class TestOpenFDALabelsFetcherSkipLimitCap:
    """25k per-query limit is enforced (max_records > 25000 gets capped)."""

    @responses.activate
    def test_max_records_capped_at_25k(self):
        # Request 30000 but only get capped at 25000
        # Return empty results so we don't need to mock 250 pages
        responses.add(
            responses.GET,
            BASE_URL,
            json={"results": []},
            status=200,
        )

        fetcher = _make_fetcher()
        result = fetcher.fetch(max_records=30_000)

        assert result["status"] == "success"
        # The fetcher should have capped max_records to FDA_SKIP_LIMIT
        # We can verify by checking it didn't try to fetch beyond 25k
        # (with empty results it stops immediately, but the cap is applied
        #  before pagination starts)
        assert result["_total_labels"] == 0

    def test_max_records_min_enforced_in_code(self):
        """Directly verify the min() logic caps at FDA_SKIP_LIMIT."""
        # This is a unit-level check: the fetch method does
        # min(int(kwargs.get('max_records', 5000)), FDA_SKIP_LIMIT)
        assert FDA_SKIP_LIMIT == 25_000

        # Requesting 50k should produce effective max of 25k
        # We test by inspecting the _paginate call indirectly
        fetcher = _make_fetcher()

        # Patch _paginate to capture the max_records it receives
        captured = {}
        original_paginate = fetcher._paginate

        def spy_paginate(search, max_records, date_str):
            captured["max_records"] = max_records
            return [], 0

        with patch.object(fetcher, "_paginate", side_effect=spy_paginate):
            fetcher.fetch(max_records=50_000)

        assert captured["max_records"] == FDA_SKIP_LIMIT


class TestOpenFDALabelsFetcherEmpty:
    """API returns no results."""

    @responses.activate
    def test_empty_results(self):
        responses.add(
            responses.GET,
            BASE_URL,
            json={"results": []},
            status=200,
        )

        fetcher = _make_fetcher()
        result = fetcher.fetch(days_back=90)

        assert result["status"] == "success"
        assert result["records"] == []
        assert result["record_count"] == 0
        assert result["_total_labels"] == 0


class TestOpenFDALabelsFetcherHTTPError:
    """HTTP errors are handled gracefully."""

    @responses.activate
    def test_http_500_on_first_page_returns_empty_success(self):
        """A 500 on the first page is caught inside _paginate; fetch returns
        success with zero records (pagination breaks but no top-level exception)."""
        responses.add(
            responses.GET,
            BASE_URL,
            json={"error": {"code": "INTERNAL_ERROR", "message": "Server error"}},
            status=500,
        )

        fetcher = _make_fetcher()
        result = fetcher.fetch(days_back=90)

        # _paginate catches the page-level exception and breaks
        assert result["status"] == "success"
        assert result["records"] == []
        assert result["record_count"] == 0
        assert result["_total_labels"] == 0

    def test_network_error_degrades_gracefully(self):
        """A connection error on the first page is caught inside _paginate and
        results in an empty success (pagination breaks, no labels collected)."""
        from requests.exceptions import ConnectionError as ReqConnError

        fetcher = _make_fetcher()
        with patch.object(fetcher.session, "get", side_effect=ReqConnError("DNS failure")):
            result = fetcher.fetch(days_back=90)

        # _paginate swallows per-page exceptions and breaks
        assert result["status"] == "success"
        assert result["records"] == []
        assert result["_total_labels"] == 0

    def test_unexpected_error_in_fetch_returns_failed(self):
        """An error raised outside _paginate (e.g. in date computation)
        triggers the top-level exception handler and returns status='failed'."""
        fetcher = _make_fetcher()
        with patch.object(fetcher, "_paginate", side_effect=RuntimeError("boom")):
            result = fetcher.fetch(days_back=90)

        assert result["status"] == "failed"
        assert "error" in result
        assert result["records"] == []


class TestOpenFDALabelsFetcherDateScoping:
    """Verify the date-based search parameter is constructed correctly."""

    @responses.activate
    def test_date_filter_includes_effective_time_range(self):
        responses.add(
            responses.GET,
            BASE_URL,
            json={"results": []},
            status=200,
        )

        fetcher = _make_fetcher()
        fetcher.fetch(days_back=90)

        assert len(responses.calls) == 1
        request_url = responses.calls[0].request.url

        # Must include effective_time range query
        assert "effective_time" in request_url
        # Should have the TO 99991231 upper bound
        assert "99991231" in request_url

    @responses.activate
    def test_custom_search_overrides_date_filter(self):
        """When search kwarg is provided, it overrides the date filter."""
        responses.add(
            responses.GET,
            BASE_URL,
            json={"results": []},
            status=200,
        )

        fetcher = _make_fetcher()
        fetcher.fetch(search="openfda.brand_name:aspirin")

        request_url = responses.calls[0].request.url
        assert "aspirin" in request_url
        # The default effective_time filter should NOT be present
        assert "effective_time" not in request_url
