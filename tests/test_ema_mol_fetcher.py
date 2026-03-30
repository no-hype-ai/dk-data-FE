"""Tests for EMA EPAR molecule fetcher.

Feature: 019-cms-puf-platform-reconciliation

Tests use mocked HTTP responses — no external network calls are made.
Verifies:
- Fetcher returns correct result shape {status, records, hash}
- Each record is a non-empty dict (one per EPAR product row)
- HTTP / download failures produce status='failed' or status='source_unavailable'
"""

import tempfile
from unittest.mock import MagicMock, patch


def _make_fetcher():
    with tempfile.TemporaryDirectory() as tmpdir:
        from dk_data.ingestion.fetchers.ema_mol import EMAMolFetcher
        return EMAMolFetcher(data_dir=tmpdir)


def _sample_rows():
    return [
        {
            "Authorisation number": "EU/1/01/001",
            "Name of medicine": "Testamol",
            "Active substance": "testamolide",
            "ATC code": "A01AA01",
            "Marketing-authorisation holder": "Test Pharma AG",
            "Authorisation status": "Authorised",
            "Date of issue of marketing authorisation": "2001-01-15",
        },
        {
            "Authorisation number": "EU/1/02/002",
            "Name of medicine": "Placebex",
            "Active substance": "placeboside",
            "ATC code": "A01AB01",
            "Marketing-authorisation holder": "Placebo Inc.",
            "Authorisation status": "Authorised",
            "Date of issue of marketing authorisation": "2002-03-20",
        },
    ]


# ---------------------------------------------------------------------------
# Tests: result shape
# ---------------------------------------------------------------------------

def test_fetch_returns_success_shape():
    fetcher = _make_fetcher()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.content = b"fake xlsx content"

    with patch.object(fetcher.session, "get", return_value=mock_resp), \
         patch.object(fetcher, "_parse_xlsx", return_value=_sample_rows()):
        result = fetcher.fetch()

    assert result["status"] == "success"
    assert result["record_count"] == 2
    assert len(result["records"]) == 2
    assert "hash" in result


def test_fetch_records_are_dicts():
    fetcher = _make_fetcher()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.content = b"fake xlsx content"

    with patch.object(fetcher.session, "get", return_value=mock_resp), \
         patch.object(fetcher, "_parse_xlsx", return_value=_sample_rows()):
        result = fetcher.fetch()

    for rec in result["records"]:
        assert isinstance(rec, dict)
        assert len(rec) > 0


def test_fetch_http_error_returns_source_unavailable():
    fetcher = _make_fetcher()
    with patch.object(fetcher.session, "get", side_effect=Exception("Connection refused")):
        result = fetcher.fetch()

    assert result["status"] in ("failed", "source_unavailable")
    assert "error" in result


def test_fetch_empty_sheet_returns_failed():
    fetcher = _make_fetcher()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.content = b"fake xlsx content"

    with patch.object(fetcher.session, "get", return_value=mock_resp), \
         patch.object(fetcher, "_parse_xlsx", return_value=[]):
        result = fetcher.fetch()

    assert result["status"] in ("failed", "source_unavailable")
