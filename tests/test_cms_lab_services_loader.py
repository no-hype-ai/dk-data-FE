"""Tests for cms_lab_services loader (019-cms-puf-platform-reconciliation T017)."""

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
    "Rndrng_NPI,Rndrng_Prvdr_Last_Org_Name,Rndrng_Prvdr_City,"
    "Rndrng_Prvdr_State_Abrvtn,Rndrng_Prvdr_Zip5,Rndrng_Prvdr_Type,"
    "HCPCS_Cd,HCPCS_Desc,"
    "Tot_Benes,Tot_Srvcs,Tot_Mdcr_Alowd_Amt,"
    "Avg_Mdcr_Alowd_Amt,Avg_Mdcr_Pymt_Amt,Avg_Mdcr_Stdzd_Amt\n"
    "5555555555,Lab Corp,Columbus,OH,43215,Clinical Lab,"
    "80053,Metabolic Panel,"
    "300,600,12000.00,"
    "20.00,16.00,15.50\n"
)

MODULE = "dk_data.ingestion.sources.cms_lab_services"


def test_loader_returns_success_result_shape():
    from dk_data.ingestion.sources.cms_lab_services import load_cms_lab_services

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT.encode("utf-8"))
        path = f.name

    with patch(f"{MODULE}.get_cursor") as mock_gc, patch(
        f"{MODULE}.upsert_records"
    ) as mock_ur:
        mock_gc.return_value = _get_cursor_ctx(0)
        mock_ur.return_value = 1
        result = load_cms_lab_services(path)

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
    from dk_data.ingestion.sources.cms_lab_services import load_cms_lab_services

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT.encode("utf-8"))
        path = f.name

    with patch(f"{MODULE}.get_cursor") as mock_gc:
        mock_gc.return_value = _get_cursor_ctx(1)
        result = load_cms_lab_services(path)

    assert result["status"] == "skipped"
    assert result["records_inserted"] == 0


def test_loader_does_not_call_log_to_meta():
    from dk_data.ingestion.sources.cms_lab_services import load_cms_lab_services

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT.encode("utf-8"))
        path = f.name

    with patch(f"{MODULE}.get_cursor") as mock_gc, patch(
        f"{MODULE}.upsert_records"
    ) as mock_ur, patch(f"{MODULE}.log_to_meta", create=True) as mock_ltm:
        mock_gc.return_value = _get_cursor_ctx(0)
        mock_ur.return_value = 1
        load_cms_lab_services(path)
        mock_ltm.assert_not_called()


def test_fetcher_source_name():
    from dk_data.ingestion.fetchers.cms_lab_services import CMSLabServicesFetcher

    assert CMSLabServicesFetcher.SOURCE_NAME == "cms_lab_services"
