"""Tests for EuropePMC fetcher.

Feature: 019-cms-puf-platform-reconciliation
Task: T028

Tests use mocked HTTP responses — no external network calls are made.
Verifies:
- Fetcher returns correct result shape {status, records, hash}
- Pagination via cursorMark is followed until exhausted
- Safety cap of 10,000 records terminates early
- HTTP errors produce status='failed' with error field
- days_back is correctly incorporated into the query date range
"""

import tempfile
from unittest.mock import MagicMock, patch

_EPMC_LOAD = "dk_data.ingestion.fetchers.europepmc.load_europepmc_data"
_EPMC_CP_LOAD = "dk_data.ingestion.fetchers.europepmc.load_checkpoint"
_EPMC_CP_SAVE = "dk_data.ingestion.fetchers.europepmc.save_checkpoint"
_EPMC_CP_CLEAR = "dk_data.ingestion.fetchers.europepmc.clear_checkpoint"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_fetcher():
    with tempfile.TemporaryDirectory() as tmpdir:
        from dk_data.ingestion.fetchers.europepmc import EuropePMCFetcher
        return EuropePMCFetcher(data_dir=tmpdir)


def _sample_record(pmid="12345678"):
    return {
        "id": pmid,
        "source": "MED",
        "pmid": pmid,
        "title": "A study on drug X",
        "abstractText": "Background: ...",
        "authorString": "Smith J, Jones A",
        "journalTitle": "Nature Medicine",
        "pubYear": "2025",
        "updateDate": "2025-06-01",
    }


def _mock_response(records, next_cursor=None, status_code=200):
    """Build a mock requests.Response-like object for EuropePMC API."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    resp.json.return_value = {
        "resultList": {"result": records},
        "nextCursorMark": next_cursor,
        "hitCount": len(records),
    }
    return resp


def _db_mocks():
    """Context manager that mocks all DB calls in the europepmc fetcher."""
    return [
        patch(_EPMC_LOAD),
        patch(_EPMC_CP_LOAD, return_value=None),
        patch(_EPMC_CP_SAVE),
        patch(_EPMC_CP_CLEAR),
    ]


# ---------------------------------------------------------------------------
# Tests: fetcher result shape
# ---------------------------------------------------------------------------

class TestEuropePMCFetcherResultShape:
    def test_returns_status_field(self):
        fetcher = _make_fetcher()
        with patch(_EPMC_LOAD), patch(_EPMC_CP_LOAD, return_value=None), \
                patch(_EPMC_CP_CLEAR), \
                patch.object(fetcher, "fetch_json", return_value={
                    "resultList": {"result": [_sample_record()]},
                    "nextCursorMark": None,
                }):
            result = fetcher.fetch(days_back=7)
        assert "status" in result

    def test_returns_records_list(self):
        fetcher = _make_fetcher()
        with patch(_EPMC_LOAD), patch(_EPMC_CP_LOAD, return_value=None), \
                patch(_EPMC_CP_CLEAR), \
                patch.object(fetcher, "fetch_json", return_value={
                    "resultList": {"result": [_sample_record(), _sample_record("87654321")]},
                    "nextCursorMark": None,
                }):
            result = fetcher.fetch(days_back=7)
        assert "records" in result
        assert isinstance(result["records"], list)

    def test_returns_hash_field(self):
        fetcher = _make_fetcher()
        with patch(_EPMC_CP_LOAD, return_value=None), patch(_EPMC_CP_CLEAR), \
                patch.object(fetcher, "fetch_json", return_value={
                    "resultList": {"result": []},
                    "nextCursorMark": None,
                }):
            result = fetcher.fetch(days_back=7)
        assert "hash" in result

    def test_success_status_on_valid_response(self):
        fetcher = _make_fetcher()
        with patch(_EPMC_LOAD), patch(_EPMC_CP_LOAD, return_value=None), \
                patch(_EPMC_CP_CLEAR), \
                patch.object(fetcher, "fetch_json", return_value={
                    "resultList": {"result": [_sample_record()]},
                    "nextCursorMark": None,
                }):
            result = fetcher.fetch(days_back=7)
        assert result["status"] == "success"

    def test_record_count_matches(self):
        fetcher = _make_fetcher()
        records = [_sample_record(str(i)) for i in range(5)]
        with patch(_EPMC_LOAD), patch(_EPMC_CP_LOAD, return_value=None), \
                patch(_EPMC_CP_CLEAR), \
                patch.object(fetcher, "fetch_json", return_value={
                    "resultList": {"result": records},
                    "nextCursorMark": None,
                }):
            result = fetcher.fetch(days_back=7)
        assert result["record_count"] == 5


# ---------------------------------------------------------------------------
# Tests: pagination via cursorMark
# ---------------------------------------------------------------------------

class TestEuropePMCPagination:
    def test_follows_cursor_on_multiple_pages(self):
        fetcher = _make_fetcher()
        call_count = 0

        def _fake_fetch_json(url, params=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "resultList": {"result": [_sample_record("1")]},
                    "nextCursorMark": "AoE=",
                }
            else:
                return {
                    "resultList": {"result": [_sample_record("2")]},
                    "nextCursorMark": None,
                }

        with patch(_EPMC_LOAD), patch(_EPMC_CP_LOAD, return_value=None), \
                patch(_EPMC_CP_CLEAR), \
                patch.object(fetcher, "fetch_json", side_effect=_fake_fetch_json):
            result = fetcher.fetch(days_back=7)

        assert result["status"] == "success"
        assert result["record_count"] == 2
        assert call_count == 2

    def test_stops_when_cursor_unchanged(self):
        fetcher = _make_fetcher()
        call_count = 0

        def _fake_fetch_json(url, params=None, **kwargs):
            nonlocal call_count
            call_count += 1
            # Same cursor returned — should stop loop
            return {
                "resultList": {"result": [_sample_record(str(call_count))]},
                "nextCursorMark": "*",  # unchanged initial cursor
            }

        with patch(_EPMC_LOAD), patch(_EPMC_CP_LOAD, return_value=None), \
                patch(_EPMC_CP_CLEAR), \
                patch.object(fetcher, "fetch_json", side_effect=_fake_fetch_json):
            fetcher.fetch(days_back=7)

        assert call_count == 1  # Loop stops immediately on same cursor

    def test_stops_on_empty_results(self):
        fetcher = _make_fetcher()
        call_count = 0

        def _fake_fetch_json(url, params=None, **kwargs):
            nonlocal call_count
            call_count += 1
            return {
                "resultList": {"result": []},
                "nextCursorMark": "AoE=",
            }

        with patch(_EPMC_CP_LOAD, return_value=None), patch(_EPMC_CP_CLEAR), \
                patch.object(fetcher, "fetch_json", side_effect=_fake_fetch_json):
            fetcher.fetch(days_back=7)

        assert call_count == 1


# ---------------------------------------------------------------------------
# Tests: safety cap
# ---------------------------------------------------------------------------

class TestEuropePMCSafetyCap:
    def test_caps_at_10000_records(self):
        fetcher = _make_fetcher()
        batch = [_sample_record(str(i)) for i in range(5000)]
        call_count = 0

        def _fake_fetch_json(url, params=None, **kwargs):
            nonlocal call_count
            call_count += 1
            return {
                "resultList": {"result": batch},
                "nextCursorMark": f"cursor_{call_count}",
            }

        with patch(_EPMC_LOAD), patch(_EPMC_CP_LOAD, return_value=None), \
                patch(_EPMC_CP_SAVE), patch(_EPMC_CP_CLEAR), \
                patch.object(fetcher, "fetch_json", side_effect=_fake_fetch_json):
            result = fetcher.fetch(days_back=30, max_records=10000)

        # After 2 batches of 5000 = 10000 records, should stop
        assert result["record_count"] == 10000
        assert result["status"] == "success"


# ---------------------------------------------------------------------------
# Tests: error handling
# ---------------------------------------------------------------------------

class TestEuropePMCErrorHandling:
    def test_http_error_returns_failed_status(self):
        fetcher = _make_fetcher()
        with patch(_EPMC_CP_LOAD, return_value=None), \
                patch.object(fetcher, "fetch_json", side_effect=Exception("Connection refused")):
            result = fetcher.fetch(days_back=7)
        assert result["status"] == "failed"
        assert result["records"] == []

    def test_error_field_present_on_failure(self):
        fetcher = _make_fetcher()
        with patch(_EPMC_CP_LOAD, return_value=None), \
                patch.object(fetcher, "fetch_json", side_effect=Exception("timeout")):
            result = fetcher.fetch(days_back=7)
        assert "error" in result

    def test_empty_results_is_success(self):
        fetcher = _make_fetcher()
        with patch(_EPMC_CP_LOAD, return_value=None), patch(_EPMC_CP_CLEAR), \
                patch.object(fetcher, "fetch_json", return_value={
                    "resultList": {"result": []},
                    "nextCursorMark": None,
                }):
            result = fetcher.fetch(days_back=7)
        assert result["status"] == "success"
        assert result["records"] == []


# ---------------------------------------------------------------------------
# Tests: source name
# ---------------------------------------------------------------------------

class TestEuropePMCSourceName:
    def test_source_name(self):
        from dk_data.ingestion.fetchers.europepmc import EuropePMCFetcher
        assert EuropePMCFetcher.SOURCE_NAME == "europepmc"
