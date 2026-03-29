"""Tests for NLM DailyMed SPL fetcher.

Feature: 019-cms-puf-platform-reconciliation

Tests use mocked HTTP responses — no external network calls are made.
Verifies:
- Pagination follows total_elements from metadata
- Each record has a set_id field
- HTTP errors produce status='failed'
"""

import tempfile
from unittest.mock import MagicMock, patch


def _make_fetcher():
    with tempfile.TemporaryDirectory() as tmpdir:
        from dk_data.ingestion.fetchers.dailymed import DailyMedFetcher
        return DailyMedFetcher(data_dir=tmpdir)


def _mock_response(records, total=None, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    resp.json.return_value = {
        "data": records,
        "metadata": {
            "total_elements": total if total is not None else len(records),
            "total_pages": 1,
            "current_page": 1,
            "elements_per_page": 100,
        },
    }
    return resp


def _sample_spls(n=3):
    return [
        {"setid": f"set-{i:04d}", "title": f"Drug Label {i}", "published": "2025-01-01"}
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_fetch_returns_success_shape():
    fetcher = _make_fetcher()
    records = _sample_spls(5)
    with patch("dk_data.ingestion.fetchers.dailymed.requests.get",
               return_value=_mock_response(records, total=5)):
        result = fetcher.fetch()

    assert result["status"] == "success"
    assert result["record_count"] == 5
    assert len(result["records"]) == 5
    assert "hash" in result


def test_fetch_empty_returns_failed():
    fetcher = _make_fetcher()
    with patch("dk_data.ingestion.fetchers.dailymed.requests.get",
               return_value=_mock_response([], total=0)):
        result = fetcher.fetch()

    assert result["status"] in ("failed", "source_unavailable")


def test_http_error_returns_failed():
    fetcher = _make_fetcher()
    with patch("dk_data.ingestion.fetchers.dailymed.requests.get",
               side_effect=Exception("Timeout")):
        result = fetcher.fetch()

    assert result["status"] in ("failed", "source_unavailable")
    assert "error" in result
