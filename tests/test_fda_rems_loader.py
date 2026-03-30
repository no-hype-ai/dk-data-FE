"""Tests for FDA REMS loader.

Feature: 019-cms-puf-platform-reconciliation

Tests mock the database connection — no real DB required.
Verifies:
- Empty records returns success immediately without DB calls
- application_number used as stable request_id base
- Slashes in application_number are replaced with underscores in request_id
- DB failures produce status='partial' with error list
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

MODULE = "dk_data.ingestion.sources.fda_rems"


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


def _sample_records(n=3):
    return [
        {
            "application_number": f"NDA0{i:05d}",
            "sponsor_name": f"Pharma Corp {i}",
            "openfda": {"brand_name": [f"Brand{i}"], "generic_name": [f"drug{i}"]},
            "submissions": [{"submission_type": "REMS"}],
        }
        for i in range(1, n + 1)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_empty_records_returns_success_without_db():
    from dk_data.ingestion.sources.fda_rems import load_fda_rems_data

    with patch(f"{MODULE}.get_connection") as mock_gc:
        result = load_fda_rems_data([])

    mock_gc.assert_not_called()
    assert result["status"] == "success"
    assert result["records_fetched"] == 0
    assert result["records_inserted"] == 0


def test_loader_success_shape():
    from dk_data.ingestion.sources.fda_rems import load_fda_rems_data

    records = _sample_records(3)
    conn, cursor = _make_conn_mock()

    with patch(f"{MODULE}.get_connection") as mock_gc:
        @contextmanager
        def _ctx():
            yield conn

        mock_gc.side_effect = _ctx
        result = load_fda_rems_data(records)

    assert result["status"] == "success"
    assert result["records_fetched"] == 3
    assert result["records_inserted"] == 3
    assert result["records_failed"] == 0
    assert result["errors"] == []


def test_request_id_uses_application_number():
    from dk_data.ingestion.sources.fda_rems import load_fda_rems_data

    records = [{"application_number": "NDA012345", "submissions": []}]
    conn, cursor = _make_conn_mock()

    with patch(f"{MODULE}.get_connection") as mock_gc:
        @contextmanager
        def _ctx():
            yield conn

        mock_gc.side_effect = _ctx
        load_fda_rems_data(records)

    args = cursor.execute.call_args[0][1]
    assert args[0] == "fda_rems_NDA012345"


def test_slash_in_application_number_replaced():
    from dk_data.ingestion.sources.fda_rems import load_fda_rems_data

    records = [{"application_number": "BLA/125/678", "submissions": []}]
    conn, cursor = _make_conn_mock()

    with patch(f"{MODULE}.get_connection") as mock_gc:
        @contextmanager
        def _ctx():
            yield conn

        mock_gc.side_effect = _ctx
        load_fda_rems_data(records)

    args = cursor.execute.call_args[0][1]
    assert "/" not in args[0]
    assert args[0].startswith("fda_rems_")


def test_missing_application_number_uses_fallback():
    from dk_data.ingestion.sources.fda_rems import load_fda_rems_data

    records = [{"sponsor_name": "Anon Corp", "submissions": []}]
    conn, cursor = _make_conn_mock()

    with patch(f"{MODULE}.get_connection") as mock_gc:
        @contextmanager
        def _ctx():
            yield conn

        mock_gc.side_effect = _ctx
        result = load_fda_rems_data(records)

    assert result["records_inserted"] == 1


def test_db_error_produces_partial():
    from dk_data.ingestion.sources.fda_rems import load_fda_rems_data

    records = _sample_records(2)
    conn, cursor = _make_conn_mock(execute_side_effect=Exception("constraint violation"))

    with patch(f"{MODULE}.get_connection") as mock_gc:
        @contextmanager
        def _ctx():
            yield conn

        mock_gc.side_effect = _ctx
        result = load_fda_rems_data(records)

    assert result["status"] == "partial"
    assert result["records_failed"] == 2
    assert len(result["errors"]) > 0


def test_result_keys():
    from dk_data.ingestion.sources.fda_rems import load_fda_rems_data

    conn, _ = _make_conn_mock()

    with patch(f"{MODULE}.get_connection") as mock_gc:
        @contextmanager
        def _ctx():
            yield conn

        mock_gc.side_effect = _ctx
        result = load_fda_rems_data(_sample_records(1))

    assert set(result.keys()) == {
        "status", "records_fetched", "records_inserted", "records_failed", "errors"
    }
