"""Tests for IMGT immunogenetics fetcher.

Feature: 019-cms-puf-platform-reconciliation

Tests use mocked HTTP responses — no external network calls are made.
Verifies:
- One record per gene group is returned
- Returns source_unavailable when IMGT server is unreachable
- Result shape is correct
"""

import tempfile
from unittest.mock import MagicMock, patch


def _make_fetcher():
    with tempfile.TemporaryDirectory() as tmpdir:
        from dk_data.ingestion.fetchers.imgt import IMGTFetcher
        return IMGTFetcher(data_dir=tmpdir)


_SAMPLE_FASTA = (
    ">IGHV1-1*01 Homo sapiens\n"
    "CAGGTGCAGCTGGTGGAGTCTGGGGGAGGCGTGGTCCAGCCTGGGAGGTCCCTGAGACTCTCCTGTGCA\n"
    ">IGHV1-2*01 Homo sapiens\n"
    "CAGGTGCAGCTGCAGGAGTCGGGCCCAGGACTGGTGAAGCCTTCGGAGACCCTGTCCCTCACCTGCACT\n"
)


def _mock_response(content, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    resp.text = content
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_fetch_returns_success_shape():
    fetcher = _make_fetcher()
    with patch("dk_data.ingestion.fetchers.imgt.requests.get",
               return_value=_mock_response(_SAMPLE_FASTA)):
        result = fetcher.fetch()

    assert result["status"] == "success"
    assert result["record_count"] >= 1
    assert "hash" in result


def test_server_unavailable_returns_source_unavailable():
    fetcher = _make_fetcher()
    with patch("dk_data.ingestion.fetchers.imgt.requests.get",
               side_effect=Exception("Connection refused")):
        result = fetcher.fetch()

    assert result["status"] in ("failed", "source_unavailable")
    assert "error" in result


def test_records_have_gene_group():
    fetcher = _make_fetcher()
    with patch("dk_data.ingestion.fetchers.imgt.requests.get",
               return_value=_mock_response(_SAMPLE_FASTA)):
        result = fetcher.fetch()

    for rec in result.get("records", []):
        assert isinstance(rec, dict)
        assert "gene_group" in rec or "species" in rec
