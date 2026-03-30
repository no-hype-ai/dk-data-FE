"""Tests for FDA NDC loader.

Feature: 019-cms-puf-platform-reconciliation

Tests mock the database connection — no real DB required.
Verifies:
- Empty records returns success immediately without DB calls
- product_ndc is normalized to request_id (dashes → underscores)
- Missing product_ndc falls back to positional id
- DB failures produce status='partial' with error list
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

MODULE = "dk_data.ingestion.sources.fda_ndc"


def _make_conn_mock(execute_side_effect=None):
    cursor = MagicMock()
    if execute_side_effect:
        cursor.execute.side_effect = execute_side_effect

    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cursor


def _sample_products(n=3):
    return [
        {
            "product_ndc": f"1234{i}-001",
            "generic_name": f"generic_drug_{i}",
            "brand_name": f"Brand{i}",
            "labeler_name": f"Labeler {i}",
            "product_type": "HUMAN PRESCRIPTION DRUG",
            "dosage_form": "TABLET",
        }
        for i in range(1, n + 1)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_empty_records_returns_success_without_db():
    from dk_data.ingestion.sources.fda_ndc import load_fda_ndc_data

    with patch(f"{MODULE}.get_connection") as mock_gc:
        result = load_fda_ndc_data([])

    mock_gc.assert_not_called()
    assert result["status"] == "success"
    assert result["records_fetched"] == 0
    assert result["records_inserted"] == 0


def test_loader_success_shape():
    from dk_data.ingestion.sources.fda_ndc import load_fda_ndc_data

    products = _sample_products(3)
    conn, cursor = _make_conn_mock()

    with patch(f"{MODULE}.get_connection") as mock_gc:
        @contextmanager
        def _ctx():
            yield conn

        mock_gc.side_effect = _ctx
        result = load_fda_ndc_data(products)

    assert result["status"] == "success"
    assert result["records_fetched"] == 3
    assert result["records_inserted"] == 3
    assert result["records_failed"] == 0
    assert result["errors"] == []


def test_request_id_uses_product_ndc_with_underscores():
    from dk_data.ingestion.sources.fda_ndc import load_fda_ndc_data

    products = [{"product_ndc": "12345-678", "generic_name": "aspirin"}]
    conn, cursor = _make_conn_mock()

    with patch(f"{MODULE}.get_connection") as mock_gc:
        @contextmanager
        def _ctx():
            yield conn

        mock_gc.side_effect = _ctx
        load_fda_ndc_data(products)

    args = cursor.execute.call_args[0][1]
    assert args[0] == "fda_ndc_12345_678"
    assert "-" not in args[0]


def test_missing_product_ndc_uses_fallback():
    from dk_data.ingestion.sources.fda_ndc import load_fda_ndc_data

    products = [{"generic_name": "ibuprofen", "brand_name": "Advil"}]
    conn, cursor = _make_conn_mock()

    with patch(f"{MODULE}.get_connection") as mock_gc:
        @contextmanager
        def _ctx():
            yield conn

        mock_gc.side_effect = _ctx
        result = load_fda_ndc_data(products)

    assert result["records_inserted"] == 1
    args = cursor.execute.call_args[0][1]
    assert args[0].startswith("fda_ndc_ndc_row_")


def test_db_error_produces_partial():
    from dk_data.ingestion.sources.fda_ndc import load_fda_ndc_data

    products = _sample_products(4)
    conn, cursor = _make_conn_mock(execute_side_effect=Exception("unique violation"))

    with patch(f"{MODULE}.get_connection") as mock_gc:
        @contextmanager
        def _ctx():
            yield conn

        mock_gc.side_effect = _ctx
        result = load_fda_ndc_data(products)

    assert result["status"] == "partial"
    assert result["records_failed"] == 4
    assert result["records_inserted"] == 0
    assert len(result["errors"]) > 0


def test_result_keys():
    from dk_data.ingestion.sources.fda_ndc import load_fda_ndc_data

    conn, _ = _make_conn_mock()

    with patch(f"{MODULE}.get_connection") as mock_gc:
        @contextmanager
        def _ctx():
            yield conn

        mock_gc.side_effect = _ctx
        result = load_fda_ndc_data(_sample_products(1))

    assert set(result.keys()) == {
        "status", "records_fetched", "records_inserted", "records_failed", "errors"
    }


def test_api_endpoint_in_insert_params():
    from dk_data.ingestion.sources.fda_ndc import load_fda_ndc_data

    products = [{"product_ndc": "99999-001", "generic_name": "testdrug"}]
    conn, cursor = _make_conn_mock()

    with patch(f"{MODULE}.get_connection") as mock_gc:
        @contextmanager
        def _ctx():
            yield conn

        mock_gc.side_effect = _ctx
        load_fda_ndc_data(products)

    args = cursor.execute.call_args[0][1]
    assert "api.fda.gov/drug/ndc.json" in args[1]
