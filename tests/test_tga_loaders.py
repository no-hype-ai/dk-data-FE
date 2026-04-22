"""Unit tests for all 5 TGA Tier-A loaders.

All 5 loaders share the `_tga_common.load_tga_page_blobs` helper — single test
class parameterized across the 5 loader entry points + table names.
"""

from unittest.mock import MagicMock, patch

import pytest

from dk_data.ingestion.sources.tga_artg_medicines import (
    load_tga_artg_medicines_data,
)
from dk_data.ingestion.sources.tga_artg_devices import (
    load_tga_artg_devices_data,
)
from dk_data.ingestion.sources.tga_sara_recalls import (
    load_tga_sara_recalls_data,
)
from dk_data.ingestion.sources.tga_medicine_shortages import (
    load_tga_medicine_shortages_data,
)
from dk_data.ingestion.sources.tga_orphan_designations import (
    load_tga_orphan_designations_data,
)

LOADERS = [
    ("tga_artg_medicines", load_tga_artg_medicines_data),
    ("tga_artg_devices", load_tga_artg_devices_data),
    ("tga_sara_recalls", load_tga_sara_recalls_data),
    ("tga_medicine_shortages", load_tga_medicine_shortages_data),
    ("tga_orphan_designations", load_tga_orphan_designations_data),
]


def _page_blob(source_id: str, n_records: int = 5) -> dict:
    return {
        "_request_id": f"{source_id}_test_skip0000000",
        "_page_number": 0,
        "results": [{"idx": i, "value": f"row-{i}"} for i in range(n_records)],
    }


@pytest.mark.parametrize("source_id,loader", LOADERS)
class TestTgaLoaders:
    """Mirrors the test_openfda_device_*_loader.py pattern — happy, empty, error."""

    def test_single_page_inserts(self, source_id, loader):
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # The helper lives in _tga_common; patch its get_connection.
        with patch(
            "dk_data.ingestion.sources._tga_common.get_connection"
        ) as mock_get_conn:
            mock_get_conn.return_value.__enter__.return_value = mock_conn
            result = loader([_page_blob(source_id, 5)])

        assert result["status"] == "success"
        assert result["records_fetched"] == 1
        assert result["records_inserted"] == 1
        assert result["records_failed"] == 0
        assert mock_cursor.execute.called

    def test_no_records(self, source_id, loader):
        result = loader([])
        assert result["status"] == "success"
        assert result["records_fetched"] == 0
        assert result["records_inserted"] == 0

    def test_db_error_recorded(self, source_id, loader):
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("connection refused")
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch(
            "dk_data.ingestion.sources._tga_common.get_connection"
        ) as mock_get_conn:
            mock_get_conn.return_value.__enter__.return_value = mock_conn
            result = loader([_page_blob(source_id, 3)])

        assert result["records_failed"] == 1
        assert result["records_inserted"] == 0
        assert "connection refused" in result["errors"][0]["error"]
