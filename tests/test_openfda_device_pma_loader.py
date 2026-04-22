"""Tests for OpenFDA Device PMA loader with mocked DB cursor."""

from unittest.mock import MagicMock, patch

from dk_data.ingestion.sources.openfda_device_pma import (
    load_openfda_device_pma_data,
)


def _page_blob(n_records: int, request_id: str = "fda_device_pma_test_skip0000000") -> dict:
    return {
        "_request_id": request_id,
        "_page_number": 0,
        "results": [
            {
                "pma_number": f"P03000{i}",
                "supplement_number": "0",
                "applicant": f"Regeneron {i}",
                "device_name": f"Drug-Eluting Stent {i}",
                "product_code": "MAF",
                "decision_date": "2026-02-20",
            }
            for i in range(n_records)
        ],
    }


class TestHappyPath:
    def test_single_page(self):
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch(
            "dk_data.ingestion.sources.openfda_device_pma.get_connection"
        ) as mock_get_conn:
            mock_get_conn.return_value.__enter__.return_value = mock_conn
            result = load_openfda_device_pma_data([_page_blob(5)])

        assert result["status"] == "success"
        assert result["records_inserted"] == 1


class TestEmpty:
    def test_no_records(self):
        result = load_openfda_device_pma_data([])
        assert result["status"] == "success"
        assert result["records_fetched"] == 0


class TestErrorHandling:
    def test_db_error(self):
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("db down")
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch(
            "dk_data.ingestion.sources.openfda_device_pma.get_connection"
        ) as mock_get_conn:
            mock_get_conn.return_value.__enter__.return_value = mock_conn
            result = load_openfda_device_pma_data([_page_blob(5)])

        assert result["records_failed"] == 1
        assert "db down" in result["errors"][0]["error"]
