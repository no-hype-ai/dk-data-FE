"""Tests for FDA NDC fetcher — bulk ZIP download implementation.

The fetcher was rewritten (PR #249) from a paginated openFDA API approach to
downloading the daily bulk export ZIP from download.open.fda.gov.  These tests
mock HTTP responses at the session.get() level and build in-memory ZIP files to
avoid any real network calls.

Verifies:
- get_latest_url() points to the bulk download endpoint
- Successful download returns status='success' with all records
- max_records cap truncates to the exact count requested
- A ZIP with no JSON file returns status='failed'
- Connection errors return status='failed'
- HTTP 500 returns status='failed'
"""

import io
import json
import tempfile
import zipfile
from unittest.mock import MagicMock, patch


def _make_fetcher():
    with tempfile.TemporaryDirectory() as tmpdir:
        from dk_data.ingestion.fetchers.fda_ndc import FDANDCFetcher
        return FDANDCFetcher(data_dir=tmpdir)


def _make_zip_response(products, json_name="drug-ndc-0001-of-0001.json", status_code=200):
    """Build a mock response whose .content is a ZIP containing the given products list."""
    payload = json.dumps({"results": products}).encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(json_name, payload)
    zip_bytes = buf.getvalue()

    resp = MagicMock()
    resp.status_code = status_code
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    else:
        resp.raise_for_status = MagicMock()
    resp.content = zip_bytes
    return resp


def _sample_products(n=3):
    return [
        {
            "product_ndc": f"1234{i}-001",
            "generic_name": f"generic_drug_{i}",
            "brand_name": f"Brand{i}",
            "labeler_name": f"Labeler {i}",
            "product_type": "HUMAN PRESCRIPTION DRUG",
            "dosage_form": "TABLET",
            "route": ["ORAL"],
            "packaging": [{"package_ndc": f"1234{i}-001-01"}],
        }
        for i in range(1, n + 1)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_source_name():
    from dk_data.ingestion.fetchers.fda_ndc import FDANDCFetcher
    assert FDANDCFetcher.SOURCE_NAME == "fda_ndc"


def test_get_latest_url():
    fetcher = _make_fetcher()
    url = fetcher.get_latest_url()
    assert "download.open.fda.gov" in url
    assert url.endswith(".zip")
    assert url.startswith("https://")


def test_fetch_returns_success_shape():
    fetcher = _make_fetcher()
    products = _sample_products(5)

    with patch.object(fetcher.session, "get", return_value=_make_zip_response(products)):
        result = fetcher.fetch()

    assert result["status"] == "success"
    assert result["record_count"] == 5
    assert len(result["records"]) == 5
    assert "hash" in result


def test_max_records_truncates_exactly():
    fetcher = _make_fetcher()
    products = _sample_products(100)

    with patch.object(fetcher.session, "get", return_value=_make_zip_response(products)):
        result = fetcher.fetch(max_records=50)

    assert result["record_count"] == 50
    assert len(result["records"]) == 50


def test_zip_with_no_json_returns_failed():
    """A ZIP containing no JSON file should raise and return status='failed'."""
    fetcher = _make_fetcher()

    # Build a ZIP with a non-JSON file only
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "no json here")
    zip_bytes = buf.getvalue()

    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.content = zip_bytes

    with patch.object(fetcher.session, "get", return_value=resp):
        result = fetcher.fetch()

    assert result["status"] == "failed"
    assert "error" in result


def test_connection_error_returns_failed():
    fetcher = _make_fetcher()
    with patch.object(fetcher.session, "get", side_effect=Exception("timeout")):
        result = fetcher.fetch()

    assert result["status"] == "failed"
    assert "error" in result


def test_http_500_returns_failed():
    fetcher = _make_fetcher()
    resp = _make_zip_response([], status_code=500)
    with patch.object(fetcher.session, "get", return_value=resp):
        result = fetcher.fetch()

    assert result["status"] == "failed"
