"""Tests for cms_home_health loader (019-cms-puf-platform-reconciliation T017)."""

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
    "Rndrng_Prvdr_Id,Rndrng_Prvdr_Name,Rndrng_Prvdr_City,"
    "Rndrng_Prvdr_State_Abrvtn,Rndrng_Prvdr_Zip5,"
    "HH_Srvc_Cd,HH_Srvc_Desc,Tot_Epsd_Stay,Tot_Benes,"
    "Avg_HH_Mdcr_Pymt_Amt,Avg_HH_Outlier_Pymt,Avg_Age,Female_Pct,Dual_Pct\n"
    "010001,Home Care Agency,Mobile,AL,36601,"
    "1,SKILLED NURSING CARE,200,150,"
    "900.00,25.00,72.5,58.0,22.0\n"
)

MODULE = "dk_data.ingestion.sources.cms_home_health"


def test_loader_returns_success_result_shape():
    from dk_data.ingestion.sources.cms_home_health import load_cms_home_health

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT.encode("utf-8"))
        path = f.name

    with patch(f"{MODULE}.get_cursor") as mock_gc, patch(
        f"{MODULE}.upsert_records"
    ) as mock_ur:
        mock_gc.return_value = _get_cursor_ctx(0)
        mock_ur.return_value = 1
        result = load_cms_home_health(path)

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
    from dk_data.ingestion.sources.cms_home_health import load_cms_home_health

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT.encode("utf-8"))
        path = f.name

    with patch(f"{MODULE}.get_cursor") as mock_gc:
        mock_gc.return_value = _get_cursor_ctx(1)
        result = load_cms_home_health(path)

    assert result["status"] == "skipped"
    assert result["records_inserted"] == 0


def test_loader_does_not_call_log_to_meta():
    from dk_data.ingestion.sources.cms_home_health import load_cms_home_health

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT.encode("utf-8"))
        path = f.name

    with patch(f"{MODULE}.get_cursor") as mock_gc, patch(
        f"{MODULE}.upsert_records"
    ) as mock_ur, patch(f"{MODULE}.log_to_meta", create=True) as mock_ltm:
        mock_gc.return_value = _get_cursor_ctx(0)
        mock_ur.return_value = 1
        load_cms_home_health(path)
        mock_ltm.assert_not_called()


def test_fetcher_source_name():
    from dk_data.ingestion.fetchers.cms_home_health import CMSHomeHealthFetcher

    assert CMSHomeHealthFetcher.SOURCE_NAME == "cms_home_health"
