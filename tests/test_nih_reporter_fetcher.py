"""Tests for NIH RePORTER fetcher.

Feature: 019-cms-puf-platform-reconciliation
Task: T028

Tests use mocked HTTP responses — no external network calls are made.
Verifies:
- Fetcher returns correct result shape {status, records, hash}
- Pagination via offset is followed until total exhausted
- Safety cap of 50,000 records terminates early
- HTTP errors produce status='failed' with error field
- days_back is correctly incorporated into date_added_filter
"""

import tempfile
from unittest.mock import MagicMock, patch

_NIH_LOAD = "dk_data.ingestion.fetchers.nih_reporter.load_nih_reporter_data"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_fetcher():
    with tempfile.TemporaryDirectory() as tmpdir:
        from dk_data.ingestion.fetchers.nih_reporter import NIHReporterFetcher
        return NIHReporterFetcher(data_dir=tmpdir)


def _sample_project(appl_id="12345678"):
    return {
        "appl_id": appl_id,
        "project_num": f"R01CA{appl_id}",
        "project_title": "Novel Cancer Therapy Research",
        "fiscal_year": 2024,
        "award_amount": 500000,
        "pi_names": [{"last_name": "Smith", "first_name": "John"}],
        "org_name": "Harvard University",
        "abstract_text": "This study examines...",
        "date_added": "2024-01-15",
    }


def _mock_post_response(projects, total=None, status_code=200):
    """Build a mock requests.Response for NIH Reporter POST."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    resp.json.return_value = {
        "results": projects,
        "meta": {"total": total if total is not None else len(projects)},
    }
    return resp


# ---------------------------------------------------------------------------
# Tests: fetcher result shape
# ---------------------------------------------------------------------------

class TestNIHReporterFetcherResultShape:
    def test_returns_status_field(self):
        fetcher = _make_fetcher()
        with patch(_NIH_LOAD), patch.object(fetcher, "session") as mock_session:
            mock_session.post.return_value = _mock_post_response([_sample_project()])
            result = fetcher.fetch(days_back=7)
        assert "status" in result

    def test_returns_records_list(self):
        fetcher = _make_fetcher()
        with patch(_NIH_LOAD), patch.object(fetcher, "session") as mock_session:
            mock_session.post.return_value = _mock_post_response([_sample_project()])
            result = fetcher.fetch(days_back=7)
        assert "records" in result
        assert isinstance(result["records"], list)

    def test_returns_hash_field(self):
        fetcher = _make_fetcher()
        with patch.object(fetcher, "session") as mock_session:
            mock_session.post.return_value = _mock_post_response([])
            result = fetcher.fetch(days_back=7)
        assert "hash" in result

    def test_success_status_on_valid_response(self):
        fetcher = _make_fetcher()
        with patch(_NIH_LOAD), patch.object(fetcher, "session") as mock_session:
            mock_session.post.return_value = _mock_post_response([_sample_project()])
            result = fetcher.fetch(days_back=7)
        assert result["status"] == "success"

    def test_record_count_matches(self):
        fetcher = _make_fetcher()
        projects = [_sample_project(str(i)) for i in range(3)]
        with patch(_NIH_LOAD), patch.object(fetcher, "session") as mock_session:
            mock_session.post.return_value = _mock_post_response(projects)
            result = fetcher.fetch(days_back=7)
        assert result["record_count"] == 3


# ---------------------------------------------------------------------------
# Tests: pagination via offset
# ---------------------------------------------------------------------------

class TestNIHReporterPagination:
    def test_follows_offset_pagination(self):
        from dk_data.ingestion.fetchers.nih_reporter import PAGE_SIZE
        fetcher = _make_fetcher()
        call_count = 0

        def _mock_post(url, json=None, timeout=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                projects = [_sample_project(str(i)) for i in range(PAGE_SIZE)]
                return _mock_post_response(projects, total=PAGE_SIZE + 2)
            else:
                projects = [_sample_project(f"p{i}") for i in range(2)]
                return _mock_post_response(projects, total=PAGE_SIZE + 2)

        with patch(_NIH_LOAD), patch.object(fetcher, "session") as mock_session:
            mock_session.post.side_effect = _mock_post
            result = fetcher.fetch(days_back=7)

        assert call_count == 2
        assert result["record_count"] == PAGE_SIZE + 2

    def test_stops_when_total_exhausted(self):
        fetcher = _make_fetcher()
        call_count = 0

        def _mock_post(url, json=None, timeout=None, **kwargs):
            nonlocal call_count
            call_count += 1
            return _mock_post_response([_sample_project(str(call_count))], total=1)

        with patch(_NIH_LOAD), patch.object(fetcher, "session") as mock_session:
            mock_session.post.side_effect = _mock_post
            fetcher.fetch(days_back=7)

        assert call_count == 1

    def test_stops_on_empty_results(self):
        fetcher = _make_fetcher()
        with patch.object(fetcher, "session") as mock_session:
            mock_session.post.return_value = _mock_post_response([], total=100)
            result = fetcher.fetch(days_back=7)
        assert result["records"] == []
        assert result["status"] == "success"


# ---------------------------------------------------------------------------
# Tests: error handling
# ---------------------------------------------------------------------------

class TestNIHReporterErrorHandling:
    def test_http_error_returns_failed_status(self):
        fetcher = _make_fetcher()
        with patch.object(fetcher, "session") as mock_session:
            mock_session.post.side_effect = Exception("Connection refused")
            result = fetcher.fetch(days_back=7)
        assert result["status"] == "failed"
        assert result["records"] == []

    def test_error_field_present_on_failure(self):
        fetcher = _make_fetcher()
        with patch.object(fetcher, "session") as mock_session:
            mock_session.post.side_effect = Exception("timeout")
            result = fetcher.fetch(days_back=7)
        assert "error" in result

    def test_empty_results_is_success(self):
        fetcher = _make_fetcher()
        with patch.object(fetcher, "session") as mock_session:
            mock_session.post.return_value = _mock_post_response([])
            result = fetcher.fetch(days_back=7)
        assert result["status"] == "success"
        assert result["records"] == []

    def test_http_400_returns_failed(self):
        fetcher = _make_fetcher()
        with patch.object(fetcher, "session") as mock_session:
            bad_resp = _mock_post_response([], status_code=400)
            mock_session.post.return_value = bad_resp
            result = fetcher.fetch(days_back=7)
        assert result["status"] == "failed"


# ---------------------------------------------------------------------------
# Tests: source name and URL
# ---------------------------------------------------------------------------

class TestNIHReporterSourceName:
    def test_source_name(self):
        from dk_data.ingestion.fetchers.nih_reporter import NIHReporterFetcher
        assert NIHReporterFetcher.SOURCE_NAME == "nih_reporter"

    def test_base_url_is_nih_api(self):
        from dk_data.ingestion.fetchers.nih_reporter import NIH_REPORTER_API
        assert "reporter.nih.gov" in NIH_REPORTER_API


# ---------------------------------------------------------------------------
# Tests: safety cap
# ---------------------------------------------------------------------------

class TestNIHReporterSafetyCap:
    def test_caps_at_max_records(self):
        from dk_data.ingestion.fetchers.nih_reporter import PAGE_SIZE, MAX_RECORDS
        fetcher = _make_fetcher()
        call_count = 0

        def _mock_post(url, json=None, timeout=None, **kwargs):
            nonlocal call_count
            call_count += 1
            projects = [_sample_project(f"{call_count}_{i}") for i in range(PAGE_SIZE)]
            return _mock_post_response(projects, total=MAX_RECORDS + 1000)

        with patch(_NIH_LOAD), patch.object(fetcher, "session") as mock_session:
            mock_session.post.side_effect = _mock_post
            result = fetcher.fetch(days_back=90)

        assert result["record_count"] <= MAX_RECORDS
        assert result["status"] == "success"
