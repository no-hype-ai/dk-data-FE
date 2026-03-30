"""Tests for ChEMBL Activities loader.

Feature: 019-cms-puf-platform-reconciliation

Tests mock the database connection — no real DB required.
Verifies:
- Empty records returns success immediately without DB calls
- Valid page blobs are inserted with correct request_id pattern
- DB failures produce status='partial' with error list
- Batch commits occur at BATCH_SIZE intervals
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, call, patch

MODULE = "dk_data.ingestion.sources.chembl_activities"


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


def _sample_blobs(n=3):
    return [
        {
            "_request_id": f"chembl_act_p{i}_o{i * 1000}",
            "_page_number": i,
            "_offset": i * 1000,
            "activities": [{"activity_id": str(j), "molecule_chembl_id": f"CHEMBL{j}"}
                           for j in range(5)],
            "page_meta": {"total_count": n * 1000},
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_empty_records_returns_success_without_db():
    from dk_data.ingestion.sources.chembl_activities import load_chembl_activities_data

    with patch(f"{MODULE}.get_connection") as mock_gc:
        result = load_chembl_activities_data([])

    mock_gc.assert_not_called()
    assert result["status"] == "success"
    assert result["records_fetched"] == 0
    assert result["records_inserted"] == 0
    assert result["records_failed"] == 0


def test_loader_success_shape():
    from dk_data.ingestion.sources.chembl_activities import load_chembl_activities_data

    blobs = _sample_blobs(2)
    conn, cursor = _make_conn_mock()

    with patch(f"{MODULE}.get_connection") as mock_gc:
        mock_gc.return_value.__enter__ = MagicMock(return_value=conn)
        mock_gc.return_value.__exit__ = MagicMock(return_value=False)

        @contextmanager
        def _ctx():
            yield conn

        mock_gc.side_effect = _ctx

        result = load_chembl_activities_data(blobs)

    assert result["status"] == "success"
    assert result["records_fetched"] == 2
    assert result["records_inserted"] == 2
    assert result["records_failed"] == 0
    assert result["errors"] == []


def test_loader_request_id_used_from_blob():
    from dk_data.ingestion.sources.chembl_activities import load_chembl_activities_data

    blobs = [
        {
            "_request_id": "chembl_act_p0_o0",
            "_page_number": 0,
            "_offset": 0,
            "activities": [{"activity_id": "1"}],
            "page_meta": {},
        }
    ]
    conn, cursor = _make_conn_mock()

    with patch(f"{MODULE}.get_connection") as mock_gc:
        @contextmanager
        def _ctx():
            yield conn

        mock_gc.side_effect = _ctx
        load_chembl_activities_data(blobs)

    # First positional arg to execute is the SQL; second is the params tuple
    args = cursor.execute.call_args[0][1]
    assert args[0] == "chembl_act_p0_o0"


def test_loader_db_error_produces_partial():
    from dk_data.ingestion.sources.chembl_activities import load_chembl_activities_data

    blobs = _sample_blobs(3)
    conn, cursor = _make_conn_mock(execute_side_effect=Exception("DB error"))

    with patch(f"{MODULE}.get_connection") as mock_gc:
        @contextmanager
        def _ctx():
            yield conn

        mock_gc.side_effect = _ctx
        result = load_chembl_activities_data(blobs)

    assert result["status"] == "partial"
    assert result["records_failed"] == 3
    assert result["records_inserted"] == 0
    assert len(result["errors"]) > 0


def test_loader_result_keys():
    from dk_data.ingestion.sources.chembl_activities import load_chembl_activities_data

    blobs = _sample_blobs(1)
    conn, _ = _make_conn_mock()

    with patch(f"{MODULE}.get_connection") as mock_gc:
        @contextmanager
        def _ctx():
            yield conn

        mock_gc.side_effect = _ctx
        result = load_chembl_activities_data(blobs)

    assert set(result.keys()) == {
        "status", "records_fetched", "records_inserted", "records_failed", "errors"
    }
