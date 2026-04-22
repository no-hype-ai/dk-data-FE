"""Tests for OpenFDA Device 510(k) loader with mocked DB cursor.

Verifies:
- Happy path: page blobs insert correctly
- Empty records: returns success with 0 inserted
- DB error: caught and recorded in errors list
"""

from unittest.mock import MagicMock, patch

from dk_data.ingestion.sources.openfda_device_510k import (
    load_openfda_device_510k_data,
)


def _page_blob(n_records: int, request_id: str = "fda_device_510k_test_skip0000000") -> dict:
    return {
        "_request_id": request_id,
        "_page_number": 0,
        "results": [
            {
                "k_number": f"K18000{i}",
                "applicant": f"Test Corp {i}",
                "device_name": f"Widget {i}",
                "product_code": "LNH",
                "decision_date": "2026-01-15",
            }
            for i in range(n_records)
        ],
    }


class TestHappyPath:
    def test_single_page_inserts(self):
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch(
            "dk_data.ingestion.sources.openfda_device_510k.get_connection"
        ) as mock_get_conn:
            mock_get_conn.return_value.__enter__.return_value = mock_conn
            result = load_openfda_device_510k_data([_page_blob(10)])

        assert result["status"] == "success"
        assert result["records_fetched"] == 1
        assert result["records_inserted"] == 1
        assert result["records_failed"] == 0
        assert mock_cursor.execute.called

    def test_multiple_pages(self):
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch(
            "dk_data.ingestion.sources.openfda_device_510k.get_connection"
        ) as mock_get_conn:
            mock_get_conn.return_value.__enter__.return_value = mock_conn
            blobs = [
                _page_blob(100, f"fda_device_510k_test_skip{i * 100:07d}")
                for i in range(3)
            ]
            result = load_openfda_device_510k_data(blobs)

        assert result["status"] == "success"
        assert result["records_fetched"] == 3
        assert result["records_inserted"] == 3
        assert mock_cursor.execute.call_count == 3


class TestEmpty:
    def test_no_records(self):
        result = load_openfda_device_510k_data([])
        assert result["status"] == "success"
        assert result["records_fetched"] == 0
        assert result["records_inserted"] == 0
        assert result["records_failed"] == 0


class TestErrorHandling:
    def test_db_error_recorded(self):
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("connection refused")
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch(
            "dk_data.ingestion.sources.openfda_device_510k.get_connection"
        ) as mock_get_conn:
            mock_get_conn.return_value.__enter__.return_value = mock_conn
            result = load_openfda_device_510k_data([_page_blob(5)])

        assert result["records_failed"] == 1
        assert result["records_inserted"] == 0
        assert len(result["errors"]) == 1
        assert "connection refused" in result["errors"][0]["error"]
