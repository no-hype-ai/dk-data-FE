"""Tests for FDA REMS fetcher.

Feature: 019-cms-puf-platform-reconciliation

Tests use mocked HTTP responses — no external network calls are made.
Verifies:
- Pagination stops at 404 or FDA skip limit
- application_number is normalized to top-level field
- HTTP errors produce status='failed'
"""

import tempfile
from unittest.mock import MagicMock, patch


def _make_fetcher():
    with tempfile.TemporaryDirectory() as tmpdir:
        from dk_data.ingestion.fetchers.fda_rems import FDARemsFetcher
        return FDARemsFetcher(data_dir=tmpdir)


def _mock_response(results, total=None, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    else:
        resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "results": results,
        "meta": {"results": {"total": total or len(results)}},
    }
    return resp


def _sample_records(n=3):
    return [
        {
            "application_number": f"NDA0{i:05d}",
            "sponsor_name": f"Pharma Corp {i}",
            "openfda": {
                "brand_name": [f"Brand{i}"],
                "generic_name": [f"generic{i}"],
                "application_number": [f"NDA0{i:05d}"],
            },
            "submissions": [{"submission_type": "REMS", "submission_number": "1"}],
        }
        for i in range(1, n + 1)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_source_name():
    from dk_data.ingestion.fetchers.fda_rems import FDARemsFetcher
    assert FDARemsFetcher.SOURCE_NAME == "fda_rems"


def test_get_latest_url():
    fetcher = _make_fetcher()
    url = fetcher.get_latest_url()
    assert "api.fda.gov/drug/drugsfda.json" in url
    assert "REMS" in url


def test_fetch_returns_success_shape():
    fetcher = _make_fetcher()
    records = _sample_records(3)
    call_count = [0]

    def _side_effect(url, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _mock_response(records, total=3)
        return _mock_response([])

    with patch.object(fetcher.session, "get", side_effect=_side_effect), \
         patch("time.sleep"):
        result = fetcher.fetch()

    assert result["status"] == "success"
    assert result["record_count"] == 3
    assert len(result["records"]) == 3
    assert "hash" in result


def test_application_number_normalized_to_top_level():
    """Records without top-level application_number get it from openfda."""
    fetcher = _make_fetcher()
    records = [
        {
            "sponsor_name": "Pharma A",
            "openfda": {"application_number": ["NDA012345"]},
            "submissions": [{"submission_type": "REMS"}],
        }
    ]
    call_count = [0]

    def _side_effect(url, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _mock_response(records, total=1)
        return _mock_response([])

    with patch.object(fetcher.session, "get", side_effect=_side_effect), \
         patch("time.sleep"):
        result = fetcher.fetch()

    assert result["status"] == "success"
    assert result["records"][0]["application_number"] == "NDA012345"


def test_max_records_cap():
    fetcher = _make_fetcher()
    records = _sample_records(100)

    with patch.object(fetcher.session, "get", return_value=_mock_response(records, total=10000)), \
         patch("time.sleep"):
        result = fetcher.fetch(max_records=50)

    assert result["record_count"] <= 50


def test_404_stops_pagination():
    fetcher = _make_fetcher()
    with patch.object(fetcher.session, "get", return_value=_mock_response([], status_code=404)):
        result = fetcher.fetch()

    assert result["status"] == "success"
    assert result["record_count"] == 0


def test_empty_results_returns_zero():
    fetcher = _make_fetcher()
    call_count = [0]

    def _side_effect(url, *a, **kw):
        call_count[0] += 1
        return _mock_response([], total=0)

    with patch.object(fetcher.session, "get", side_effect=_side_effect):
        result = fetcher.fetch()

    assert result["status"] == "success"
    assert result["record_count"] == 0


def test_connection_error_returns_failed():
    fetcher = _make_fetcher()
    with patch.object(fetcher.session, "get", side_effect=Exception("Connection refused")):
        result = fetcher.fetch()

    assert result["status"] == "failed"
    assert "error" in result


def test_http_500_returns_failed():
    fetcher = _make_fetcher()
    with patch.object(fetcher.session, "get", return_value=_mock_response([], status_code=500)):
        result = fetcher.fetch()

    assert result["status"] == "failed"
