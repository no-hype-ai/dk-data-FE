"""Tests for cms_cost_reports_puf loader (019-cms-puf-platform-reconciliation T017)."""

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
    "RPT_REC_NUM,PRVDR_CTRL_TYPE_CD,PRVDR_NUM,RPT_STUS_CD,INITL_RPT_SW,"
    "LAST_RPT_SW,TRNSMTL_NUM,FI_NUM,ADR_VNDR_CD,FI_CREAT_DT,"
    "UTIL_CD,NPR_DT,SPEC_IND,FI_RCPT_DT,"
    "TOTAL_BEDS,TOTAL_DISCHARGES,NET_PATIENT_REVENUE,TOTAL_OPERATING_EXPENSES\n"
    "100001,2,010001,As Submitted,Y,Y,1,00001,0,2023-01-15,"
    "G,2023-06-30,1,2023-01-10,250,8500,75000000.00,70000000.00\n"
)

MODULE = "dk_data.ingestion.sources.cms_cost_reports_puf"


def test_loader_returns_success_result_shape():
    from dk_data.ingestion.sources.cms_cost_reports_puf import (
        load_cms_cost_reports_puf,
    )

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT.encode("utf-8"))
        path = f.name

    with patch(f"{MODULE}.get_cursor") as mock_gc, patch(
        f"{MODULE}.upsert_records"
    ) as mock_ur:
        mock_gc.return_value = _get_cursor_ctx(0)
        mock_ur.return_value = 1
        result = load_cms_cost_reports_puf(path)

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
    from dk_data.ingestion.sources.cms_cost_reports_puf import (
        load_cms_cost_reports_puf,
    )

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT.encode("utf-8"))
        path = f.name

    with patch(f"{MODULE}.get_cursor") as mock_gc:
        mock_gc.return_value = _get_cursor_ctx(1)
        result = load_cms_cost_reports_puf(path)

    assert result["status"] == "skipped"
    assert result["records_inserted"] == 0


def test_loader_does_not_call_log_to_meta():
    from dk_data.ingestion.sources.cms_cost_reports_puf import (
        load_cms_cost_reports_puf,
    )

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT.encode("utf-8"))
        path = f.name

    with patch(f"{MODULE}.get_cursor") as mock_gc, patch(
        f"{MODULE}.upsert_records"
    ) as mock_ur, patch(f"{MODULE}.log_to_meta", create=True) as mock_ltm:
        mock_gc.return_value = _get_cursor_ctx(0)
        mock_ur.return_value = 1
        load_cms_cost_reports_puf(path)
        mock_ltm.assert_not_called()


def test_fetcher_source_name():
    from dk_data.ingestion.fetchers.cms_cost_reports_puf import (
        CMSCostReportsPUFFetcher,
    )

    assert CMSCostReportsPUFFetcher.SOURCE_NAME == "cms_cost_reports_puf"
