"""Tests for load_cms_coverage_data."""

import json
from unittest.mock import MagicMock, patch

import pytest

from dk_data.ingestion.sources.cms_coverage import load_cms_coverage_data


@pytest.fixture
def mock_cursor():
    cur = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=cur)
    ctx.__exit__ = MagicMock(return_value=False)
    return cur, ctx


def _make_record(coverage_id="ncd-001", endpoint="ncd", **kwargs):
    return {"id": coverage_id, "_endpoint": endpoint, "title": "Test Coverage Decision", **kwargs}


class TestLoadCmsCoverageData:
    def test_returns_success_for_empty_records(self):
        result = load_cms_coverage_data([])
        assert result["status"] == "success"
        assert result["records_fetched"] == 0
        assert result["records_inserted"] == 0

    @patch("dk_data.ingestion.sources.cms_coverage.get_cursor")
    def test_inserts_valid_records(self, mock_get_cursor):
        cur = MagicMock()
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=cur)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        records = [
            _make_record("ncd-001", "ncd"),
            _make_record("nca-001", "nca"),
        ]
        result = load_cms_coverage_data(records)

        assert result["status"] == "success"
        assert result["records_fetched"] == 2
        assert result["records_inserted"] == 2
        assert cur.execute.call_count == 2

    @patch("dk_data.ingestion.sources.cms_coverage.get_cursor")
    def test_skips_records_missing_id(self, mock_get_cursor):
        cur = MagicMock()
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=cur)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        records = [
            {"_endpoint": "ncd", "title": "No ID"},  # missing id
            _make_record("ncd-001", "ncd"),
        ]
        result = load_cms_coverage_data(records)

        assert result["records_fetched"] == 2
        assert result["records_inserted"] == 1
        assert cur.execute.call_count == 1

    @patch("dk_data.ingestion.sources.cms_coverage.get_cursor")
    def test_skips_records_missing_endpoint(self, mock_get_cursor):
        cur = MagicMock()
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=cur)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        records = [
            {"id": "ncd-001", "title": "No Endpoint"},  # missing _endpoint
            _make_record("ncd-002", "ncd"),
        ]
        result = load_cms_coverage_data(records)

        assert result["records_inserted"] == 1

    @patch("dk_data.ingestion.sources.cms_coverage.get_cursor")
    def test_returns_partial_on_db_error(self, mock_get_cursor):
        cur = MagicMock()
        cur.execute.side_effect = [None, Exception("DB constraint error")]
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=cur)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        records = [
            _make_record("ncd-001", "ncd"),
            _make_record("ncd-002", "ncd"),
        ]
        result = load_cms_coverage_data(records)

        assert result["status"] == "partial"
        assert result["records_inserted"] == 1
        assert len(result["errors"]) == 1

    @patch("dk_data.ingestion.sources.cms_coverage.get_cursor")
    def test_passes_json_to_execute(self, mock_get_cursor):
        cur = MagicMock()
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=cur)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        record = _make_record("ncd-001", "ncd", decision="Covered")
        load_cms_coverage_data([record])

        args = cur.execute.call_args[0]
        passed_json = json.loads(args[1][0])
        assert passed_json["id"] == "ncd-001"
        assert passed_json["_endpoint"] == "ncd"
        assert passed_json["decision"] == "Covered"

    @patch("dk_data.ingestion.sources.cms_coverage.get_cursor")
    def test_caps_errors_at_ten(self, mock_get_cursor):
        cur = MagicMock()
        cur.execute.side_effect = Exception("error")
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=cur)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        records = [_make_record(f"ncd-{i:03d}", "ncd") for i in range(15)]
        result = load_cms_coverage_data(records)

        assert len(result["errors"]) == 10
