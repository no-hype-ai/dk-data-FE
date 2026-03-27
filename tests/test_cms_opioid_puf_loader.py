"""Tests for cms_opioid_puf loader (019-cms-puf-platform-reconciliation T017)."""

import tempfile
from contextlib import contextmanager
from unittest.mock import MagicMock, patch


def _make_cursor_mock(count: int) -> MagicMock:
    cursor = MagicMock()
    cursor.fetchone.return_value = (count,)
    return cursor


def _get_cursor_ctx(count: int):
    @contextmanager
    def _ctx():
        yield _make_cursor_mock(count)

    return _ctx()


CSV_CONTENT = (
    "Prscrbr_NPI,Prscrbr_Last_Org_Name,Prscrbr_First_Name,"
    "Prscrbr_Type,Prscrbr_State_Abrvtn,Opioid_Drug_Flag,"
    "Extended_Release_Opioid_Drug_Flag,Tot_Clms,Tot_Opioid_Clms,"
    "Opioid_Prscrbr_Rate,Tot_Benes\n"
    "8888888888,Wilson,David,Pain Management,KY,Y,N,400,60,15.0,250\n"
)

MODULE = "dk_data.ingestion.sources.cms_opioid_puf"


def test_loader_returns_success_result_shape():
    from dk_data.ingestion.sources.cms_opioid_puf import load_cms_opioid_puf

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT.encode("utf-8"))
        path = f.name

    with patch(f"{MODULE}.get_cursor") as mock_gc, patch(
        f"{MODULE}.upsert_records"
    ) as mock_ur:
        mock_gc.return_value = _get_cursor_ctx(0)
        mock_ur.return_value = 1
        result = load_cms_opioid_puf(path)

    assert set(result.keys()) == {
        "status",
        "records_fetched",
        "records_inserted",
        "records_updated",
        "errors",
    }
    assert result["status"] == "success"
    assert result["records_fetched"] == 1


def test_loader_skips_on_duplicate_hash():
    from dk_data.ingestion.sources.cms_opioid_puf import load_cms_opioid_puf

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT.encode("utf-8"))
        path = f.name

    with patch(f"{MODULE}.get_cursor") as mock_gc:
        mock_gc.return_value = _get_cursor_ctx(1)
        result = load_cms_opioid_puf(path)

    assert result["status"] == "skipped"
    assert result["records_inserted"] == 0


def test_loader_does_not_call_log_to_meta():
    from dk_data.ingestion.sources.cms_opioid_puf import load_cms_opioid_puf

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT.encode("utf-8"))
        path = f.name

    with patch(f"{MODULE}.get_cursor") as mock_gc, patch(
        f"{MODULE}.upsert_records"
    ) as mock_ur, patch(f"{MODULE}.log_to_meta", create=True) as mock_ltm:
        mock_gc.return_value = _get_cursor_ctx(0)
        mock_ur.return_value = 1
        load_cms_opioid_puf(path)
        mock_ltm.assert_not_called()


def test_fetcher_source_name():
    from dk_data.ingestion.fetchers.cms_opioid_puf import CMSOpioidPUFFetcher

    assert CMSOpioidPUFFetcher.SOURCE_NAME == "cms_opioid_puf"
