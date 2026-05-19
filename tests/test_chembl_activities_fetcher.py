"""Tests for ChEMBL Activities fetcher.

Feature: 019-cms-puf-platform-reconciliation

Tests use mocked HTTP responses — no external network calls are made.
Verifies:
- Pagination stops when activities list is empty
- Page blobs contain _request_id, activities, page_meta keys
- max_records cap halts pagination early
- HTTP errors produce status='failed'
"""

import tempfile
from unittest.mock import MagicMock, patch


def _make_fetcher():
    with tempfile.TemporaryDirectory() as tmpdir:
        from dk_data.ingestion.fetchers.chembl_activities import ChEMBLActivitiesFetcher
        return ChEMBLActivitiesFetcher(data_dir=tmpdir)


def _mock_response(activities, total=None, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    else:
        resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "activities": activities,
        "page_meta": {"total_count": total or len(activities), "limit": 1000, "offset": 0},
    }
    return resp


def _sample_activities(n=3):
    return [
        {
            "activity_id": str(i),
            "molecule_chembl_id": f"CHEMBL{i}",
            "assay_chembl_id": f"CHEMBL_ASSAY_{i}",
            "standard_type": "IC50",
            "standard_value": "100",
            "standard_units": "nM",
        }
        for i in range(1, n + 1)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_source_name():
    from dk_data.ingestion.fetchers.chembl_activities import ChEMBLActivitiesFetcher
    assert ChEMBLActivitiesFetcher.SOURCE_NAME == "chembl_activities"


def test_get_latest_url():
    fetcher = _make_fetcher()
    url = fetcher.get_latest_url()
    assert "chembl/api/data/activity" in url
    assert url.startswith("https://")


def test_fetch_returns_success_shape():
    fetcher = _make_fetcher()
    activities = _sample_activities(3)
    call_count = [0]

    def _side_effect(url, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _mock_response(activities, total=3)
        return _mock_response([])

    with patch.object(fetcher.session, "get", side_effect=_side_effect), \
         patch("time.sleep"), \
         patch("dk_data.ingestion.fetchers.chembl_activities.load_chembl_activities_data",
               return_value={"records_inserted": 1}) as mock_load, \
         patch("dk_data.ingestion.fetchers.chembl_activities.load_checkpoint", return_value=None), \
         patch("dk_data.ingestion.fetchers.chembl_activities.clear_checkpoint"):
        result = fetcher.fetch(max_records=10)

    assert result["status"] == "success"
    assert result["record_count"] == 1  # one page blob flushed to DB
    assert result["records"] == []      # streamed directly to DB, not returned
    assert "hash" in result
    mock_load.assert_called_once()


def test_page_blob_structure():
    fetcher = _make_fetcher()
    activities = _sample_activities(2)
    call_count = [0]
    captured_blobs = []

    def _side_effect(url, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _mock_response(activities, total=2)
        return _mock_response([])

    def _capture_load(blobs):
        captured_blobs.extend(blobs)
        return {"records_inserted": len(blobs)}

    with patch.object(fetcher.session, "get", side_effect=_side_effect), \
         patch("time.sleep"), \
         patch("dk_data.ingestion.fetchers.chembl_activities.load_chembl_activities_data",
               side_effect=_capture_load), \
         patch("dk_data.ingestion.fetchers.chembl_activities.load_checkpoint", return_value=None), \
         patch("dk_data.ingestion.fetchers.chembl_activities.clear_checkpoint"):
        result = fetcher.fetch(max_records=10)

    assert result["status"] == "success"
    assert len(captured_blobs) == 1
    blob = captured_blobs[0]
    assert "_request_id" in blob
    assert "_page_number" in blob
    assert "_offset" in blob
    assert "activities" in blob
    assert "page_meta" in blob
    assert len(blob["activities"]) == 2


def test_max_records_cap_stops_pagination():
    fetcher = _make_fetcher()
    activities = _sample_activities(1000)

    with patch.object(fetcher.session, "get", return_value=_mock_response(activities, total=20_000_000)), \
         patch("time.sleep"), \
         patch("dk_data.ingestion.fetchers.chembl_activities.load_chembl_activities_data",
               return_value={"records_inserted": 1}), \
         patch("dk_data.ingestion.fetchers.chembl_activities.load_checkpoint", return_value=None), \
         patch("dk_data.ingestion.fetchers.chembl_activities.clear_checkpoint"):
        result = fetcher.fetch(max_records=500)

    # With 1000 activities per page and max_records=500, stops after first page
    assert result["status"] == "success"
    assert result["record_count"] >= 1


def test_empty_first_page_returns_zero_blobs():
    fetcher = _make_fetcher()
    with patch.object(fetcher.session, "get", return_value=_mock_response([])):
        result = fetcher.fetch(max_records=1000)

    assert result["status"] == "success"
    assert result["record_count"] == 0
    assert result["records"] == []


def test_404_stops_pagination():
    fetcher = _make_fetcher()
    with patch.object(fetcher.session, "get", return_value=_mock_response([], status_code=404)):
        result = fetcher.fetch(max_records=1000)

    assert result["status"] == "success"
    assert result["record_count"] == 0


def test_connection_error_returns_failed():
    fetcher = _make_fetcher()
    with patch.object(fetcher.session, "get", side_effect=Exception("Connection refused")):
        result = fetcher.fetch(max_records=1000)

    assert result["status"] == "failed"
    assert "error" in result


def test_http_500_returns_failed():
    fetcher = _make_fetcher()
    with patch.object(fetcher.session, "get", return_value=_mock_response([], status_code=500)):
        result = fetcher.fetch(max_records=1000)

    assert result["status"] == "failed"
    assert "error" in result
