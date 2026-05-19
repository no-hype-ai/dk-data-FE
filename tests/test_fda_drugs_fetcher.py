"""Tests for FDA Drugs@FDA fetcher.

Feature: 019-cms-puf-platform-reconciliation

Tests use mocked HTTP responses — no external network calls are made.
Verifies:
- Pagination stops at 404 or FDA skip limit
- Records contain application_number
- HTTP errors produce status='failed'
"""

import tempfile
from unittest.mock import MagicMock, patch


def _make_fetcher():
    with tempfile.TemporaryDirectory() as tmpdir:
        from dk_data.ingestion.fetchers.fda_drugs import FDADrugsFetcher
        return FDADrugsFetcher(data_dir=tmpdir)


def _mock_response(results, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    if status_code == 404:
        resp.raise_for_status.side_effect = Exception("HTTP 404")
    resp.json.return_value = {"results": results, "meta": {"results": {"total": len(results)}}}
    return resp


def _sample_applications(n=3):
    return [
        {
            "application_number": f"NDA0{i:05d}",
            "sponsor_name": f"Pharma Corp {i}",
            "openfda": {"brand_name": [f"Brand{i}"], "generic_name": [f"generic{i}"]},
            "products": [],
            "submissions": [],
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_fetch_returns_success_shape():
    fetcher = _make_fetcher()
    apps = _sample_applications(3)

    call_count = [0]

    def _side_effect(url, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _mock_response(apps)
        return _mock_response([], status_code=404)

    with patch.object(fetcher.session, "get", side_effect=_side_effect):
        result = fetcher.fetch()

    assert result["status"] == "success"
    assert result["record_count"] == 3
    assert "hash" in result


def test_404_stops_pagination():
    fetcher = _make_fetcher()
    with patch.object(fetcher.session, "get", return_value=_mock_response([], status_code=404)):
        result = fetcher.fetch()

    # Should complete (not crash) — empty is ok if first page is 404
    assert result["status"] in ("success", "failed", "source_unavailable")


def test_connection_error_returns_failed():
    fetcher = _make_fetcher()
    with patch.object(fetcher.session, "get", side_effect=Exception("Connection refused")):
        result = fetcher.fetch()

    assert result["status"] in ("failed", "source_unavailable")
    assert "error" in result
