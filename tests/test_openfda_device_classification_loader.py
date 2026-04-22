"""Tests for OpenFDA Device Classification loader with mocked DB cursor."""

from unittest.mock import MagicMock, patch

from dk_data.ingestion.sources.openfda_device_classification import (
    load_openfda_device_classification_data,
)


def _page_blob(n_records: int) -> dict:
    return {
        "_request_id": "fda_device_classification_test_skip0000000",
        "_page_number": 0,
        "results": [
            {
                "product_code": f"L{i:02d}H",
                "device_name": f"Device Type {i}",
                "device_class": "2",
                "medical_specialty_description": "Cardiology",
                "regulation_number": "870.1234",
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
            "dk_data.ingestion.sources.openfda_device_classification.get_connection"
        ) as mock_get_conn:
            mock_get_conn.return_value.__enter__.return_value = mock_conn
            result = load_openfda_device_classification_data([_page_blob(3)])

        assert result["status"] == "success"
        assert result["records_inserted"] == 1


class TestEmpty:
    def test_no_records(self):
        result = load_openfda_device_classification_data([])
        assert result["status"] == "success"
        assert result["records_fetched"] == 0


class TestErrorHandling:
    def test_db_error(self):
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("timeout")
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch(
            "dk_data.ingestion.sources.openfda_device_classification.get_connection"
        ) as mock_get_conn:
            mock_get_conn.return_value.__enter__.return_value = mock_conn
            result = load_openfda_device_classification_data([_page_blob(3)])

        assert result["records_failed"] == 1
        assert "timeout" in result["errors"][0]["error"]
