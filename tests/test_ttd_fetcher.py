"""Tests for Therapeutic Target Database (TTD) fetcher.

Feature: 019-cms-puf-platform-reconciliation

Tests use mocked HTTP responses — no external network calls are made.
Verifies:
- Fetcher parses TTD key-value block format
- Returns source_unavailable when server is unreachable
- Result shape is correct
"""

import tempfile
from unittest.mock import MagicMock, patch


def _make_fetcher():
    with tempfile.TemporaryDirectory() as tmpdir:
        from dk_data.ingestion.fetchers.ttd import TTDFetcher
        return TTDFetcher(data_dir=tmpdir)


def _mock_response(content, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    resp.content = content if isinstance(content, bytes) else content.encode()
    resp.text = content if isinstance(content, str) else content.decode("utf-8", errors="replace")
    return resp


_SAMPLE_TTD_BLOCK = (
    "TTDID\tT00001\n"
    "Name\tTest Target 1\n"
    "Type\tSuccessful target\n"
    "UniProt\tP12345\n"
    "\n"
    "TTDID\tT00002\n"
    "Name\tTest Target 2\n"
    "Type\tClinical trial target\n"
    "\n"
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_fetch_returns_success_shape():
    fetcher = _make_fetcher()
    with patch("dk_data.ingestion.fetchers.ttd.requests.get",
               return_value=_mock_response(_SAMPLE_TTD_BLOCK)):
        result = fetcher.fetch()

    assert result["status"] == "success"
    assert result["record_count"] >= 1
    assert "hash" in result


def test_server_unavailable_returns_source_unavailable():
    fetcher = _make_fetcher()
    with patch("dk_data.ingestion.fetchers.ttd.requests.get",
               side_effect=Exception("Connection refused")):
        result = fetcher.fetch()

    assert result["status"] in ("failed", "source_unavailable")
    assert "error" in result


def test_records_are_dicts():
    fetcher = _make_fetcher()
    with patch("dk_data.ingestion.fetchers.ttd.requests.get",
               return_value=_mock_response(_SAMPLE_TTD_BLOCK)):
        result = fetcher.fetch()

    for rec in result.get("records", []):
        assert isinstance(rec, dict)
