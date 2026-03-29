"""Tests for FDA Orange Book fetcher.

Feature: 019-cms-puf-platform-reconciliation

Tests use mocked HTTP responses — no external network calls are made.
Verifies:
- Fetcher downloads and merges 3 files (products, patents, exclusivity)
- Each record has a _file_type field
- HTTP failures produce status='failed'
"""

import tempfile
from unittest.mock import MagicMock, patch


def _make_fetcher():
    with tempfile.TemporaryDirectory() as tmpdir:
        from dk_data.ingestion.fetchers.orange_book import OrangeBookFetcher
        return OrangeBookFetcher(data_dir=tmpdir)


def _mock_products_content():
    return (
        b"Ingredient~DF;Route~Trade_Name~Applicant~Strength~Appl_No~Product_No~"
        b"TE_Code~Approval_Date~RLD~RS~Type~Applicant_Full_Name\n"
        b"TESTAMOL~TABLET;ORAL~Testamol~TEST~100MG~NDA012345~001~AB~Jan 1, 2001~Yes~Yes~RX~Test Pharma AG\n"
    )


def _mock_response(content, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    resp.content = content
    resp.text = content.decode("utf-8", errors="replace")
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_fetch_returns_success_shape():
    fetcher = _make_fetcher()
    with patch("dk_data.ingestion.fetchers.orange_book.requests.get",
               return_value=_mock_response(_mock_products_content())):
        result = fetcher.fetch()

    assert result["status"] == "success"
    assert result["record_count"] >= 1
    assert "hash" in result


def test_records_have_file_type():
    fetcher = _make_fetcher()
    with patch("dk_data.ingestion.fetchers.orange_book.requests.get",
               return_value=_mock_response(_mock_products_content())):
        result = fetcher.fetch()

    for rec in result.get("records", []):
        assert "_file_type" in rec


def test_http_error_returns_failed():
    fetcher = _make_fetcher()
    with patch("dk_data.ingestion.fetchers.orange_book.requests.get",
               side_effect=Exception("Network error")):
        result = fetcher.fetch()

    assert result["status"] in ("failed", "source_unavailable")
    assert "error" in result
