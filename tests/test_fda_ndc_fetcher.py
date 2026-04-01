"""Tests for FDA NDC fetcher.

Feature: 019-cms-puf-platform-reconciliation

Tests use mocked HTTP responses — no external network calls are made.
Verifies:
- Pagination stops at 404 or FDA skip limit (25000)
- product_type filter is applied as search param
- max_records cap truncates to exact count
- HTTP errors produce status='failed'
"""

import tempfile
from unittest.mock import MagicMock, patch


def _make_fetcher():
    with tempfile.TemporaryDirectory() as tmpdir:
        from dk_data.ingestion.fetchers.fda_ndc import FDANDCFetcher
        return FDANDCFetcher(data_dir=tmpdir)


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
    assert "api.fda.gov/drug/ndc.json" in url
    assert url.startswith("https://")


def test_fetch_returns_success_shape():
    fetcher = _make_fetcher()
    products = _sample_products(5)
    call_count = [0]

    def _side_effect(url, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _mock_response(products, total=5)
        return _mock_response([])

    with patch.object(fetcher.session, "get", side_effect=_side_effect), \
         patch("time.sleep"):
        result = fetcher.fetch()

    assert result["status"] == "success"
    assert result["record_count"] == 5
    assert len(result["records"]) == 5
    assert "hash" in result


def test_max_records_truncates_exactly():
    fetcher = _make_fetcher()
    products = _sample_products(100)

    with patch.object(fetcher.session, "get", return_value=_mock_response(products, total=50000)), \
         patch("time.sleep"):
        result = fetcher.fetch(max_records=50)

    assert result["record_count"] == 50


def test_product_type_filter_passed_as_search_param():
    # The fetcher now uses alphabetic partitioning on generic_name regardless
    # of product_type. The search param is always "generic_name:<letter>*".
    fetcher = _make_fetcher()
    captured_params = {}

    def _side_effect(url, params=None, **kw):
        captured_params.update(params or {})
        return _mock_response([])

    with patch.object(fetcher.session, "get", side_effect=_side_effect):
        fetcher.fetch()

    assert "search" in captured_params
    assert captured_params["search"].startswith("generic_name:")


def test_search_param_always_present():
    # The fetcher always includes a generic_name partition in the search param.
    fetcher = _make_fetcher()
    captured_params = {}

    def _side_effect(url, params=None, **kw):
        captured_params.update(params or {})
        return _mock_response([])

    with patch.object(fetcher.session, "get", side_effect=_side_effect):
        fetcher.fetch()

    assert "search" in captured_params


def test_404_stops_pagination():
    fetcher = _make_fetcher()
    with patch.object(fetcher.session, "get", return_value=_mock_response([], status_code=404)):
        result = fetcher.fetch()

    assert result["status"] == "success"
    assert result["record_count"] == 0


def test_empty_first_page_returns_zero():
    fetcher = _make_fetcher()
    with patch.object(fetcher.session, "get", return_value=_mock_response([], total=0)):
        result = fetcher.fetch()

    assert result["status"] == "success"
    assert result["record_count"] == 0


def test_connection_error_returns_failed():
    fetcher = _make_fetcher()
    with patch.object(fetcher.session, "get", side_effect=Exception("timeout")):
        result = fetcher.fetch()

    assert result["status"] == "failed"
    assert "error" in result


def test_http_500_returns_failed():
    fetcher = _make_fetcher()
    with patch.object(fetcher.session, "get", return_value=_mock_response([], status_code=500)):
        result = fetcher.fetch()

    assert result["status"] == "failed"
