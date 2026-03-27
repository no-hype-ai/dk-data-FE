"""Tests for cms_inpatient_puf loader (019-cms-puf-platform-reconciliation T017)."""

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
    "DRG Definition,Provider Id,Provider Name,Provider Street Address,"
    "Provider City,Provider State,Provider Zip Code,"
    "Hospital Referral Region (HRR) Description,"
    "Total Discharges,Average Covered Charges,Average Total Payments,Average Medicare Payments\n"
    "001 - HEART TRANSPLANT,100001,General Hospital,123 Main St,"
    "Springfield,IL,62701,IL - Springfield,50,75000.00,12000.00,10000.00\n"
)

MODULE = "dk_data.ingestion.sources.cms_inpatient_puf"


def test_loader_returns_success_result_shape():
    from dk_data.ingestion.sources.cms_inpatient_puf import load_cms_inpatient_puf

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT.encode("utf-8"))
        path = f.name

    with patch(f"{MODULE}.get_cursor") as mock_gc, patch(
        f"{MODULE}.upsert_records"
    ) as mock_ur:
        mock_gc.return_value = _get_cursor_ctx(0)
        mock_ur.return_value = 1
        result = load_cms_inpatient_puf(path)

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
    from dk_data.ingestion.sources.cms_inpatient_puf import load_cms_inpatient_puf

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT.encode("utf-8"))
        path = f.name

    with patch(f"{MODULE}.get_cursor") as mock_gc:
        mock_gc.return_value = _get_cursor_ctx(1)
        result = load_cms_inpatient_puf(path)

    assert result["status"] == "skipped"
    assert result["records_inserted"] == 0


def test_loader_does_not_call_log_to_meta():
    from dk_data.ingestion.sources.cms_inpatient_puf import load_cms_inpatient_puf

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT.encode("utf-8"))
        path = f.name

    with patch(f"{MODULE}.get_cursor") as mock_gc, patch(
        f"{MODULE}.upsert_records"
    ) as mock_ur, patch(f"{MODULE}.log_to_meta", create=True) as mock_ltm:
        mock_gc.return_value = _get_cursor_ctx(0)
        mock_ur.return_value = 1
        load_cms_inpatient_puf(path)
        mock_ltm.assert_not_called()


def test_fetcher_source_name():
    from dk_data.ingestion.fetchers.cms_inpatient_puf import CMSInpatientPUFFetcher

    assert CMSInpatientPUFFetcher.SOURCE_NAME == "cms_inpatient_puf"
