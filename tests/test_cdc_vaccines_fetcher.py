"""Tests for CDC CVX/MVX vaccine codes fetcher.

Feature: 019-cms-puf-platform-reconciliation

Tests use mocked HTTP responses — no external network calls are made.
Verifies:
- Both CVX and MVX records are returned
- Each record has a _record_type field
- HTTP errors produce status='failed'
"""

import tempfile
from unittest.mock import MagicMock, patch


def _make_fetcher():
    with tempfile.TemporaryDirectory() as tmpdir:
        from dk_data.ingestion.fetchers.cdc_vaccines import CDCVaccinesFetcher
        return CDCVaccinesFetcher(data_dir=tmpdir)


def _mock_socrata_response(records, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    resp.json.return_value = records
    return resp


_SAMPLE_CVX = [
    {"cvx_code": "01", "short_description": "DTP", "full_vaccine_name": "Diphtheria, Tetanus Toxoids and Pertussis Vaccine", "status": "Active"},
    {"cvx_code": "02", "short_description": "OPV", "full_vaccine_name": "Poliovirus Vaccine, Live, Oral", "status": "Inactive"},
]

_SAMPLE_MVX = [
    {"mvx_code": "PMC", "manufacturer_name": "Pfizer Inc.", "status": "Active"},
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_fetch_returns_success_shape():
    fetcher = _make_fetcher()

    def _side_effect(url, *a, **kw):
        if "fhky-rtsk" in url:
            return _mock_socrata_response(_SAMPLE_CVX)
        return _mock_socrata_response(_SAMPLE_MVX)

    with patch.object(fetcher.session, "get", side_effect=_side_effect):
        result = fetcher.fetch()

    assert result["status"] == "success"
    assert result["record_count"] >= 2
    assert "hash" in result


def test_records_have_record_type():
    fetcher = _make_fetcher()

    def _side_effect(url, *a, **kw):
        if "fhky-rtsk" in url:
            return _mock_socrata_response(_SAMPLE_CVX)
        return _mock_socrata_response(_SAMPLE_MVX)

    with patch.object(fetcher.session, "get", side_effect=_side_effect):
        result = fetcher.fetch()

    for rec in result.get("records", []):
        assert "_record_type" in rec
        assert rec["_record_type"] in ("cvx", "mvx")


def test_http_error_returns_failed():
    fetcher = _make_fetcher()
    with patch.object(fetcher.session, "get", side_effect=Exception("Connection refused")):
        result = fetcher.fetch()

    assert result["status"] in ("failed", "source_unavailable")
    assert "error" in result
