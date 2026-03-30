"""Tests for cms_geographic_variation loader (019-cms-puf-platform-reconciliation T017)."""

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
    "Bene_Geo_Lvl,Bene_State_Abrvtn,Bene_State_Desc,Bene_County_Desc,"
    "Bene_FIPS_Cd,Year,Tot_Mdcr_Enrlees,Tot_Mdcr_Pymt_Amt,"
    "Avg_Mdcr_Pymt_Amt,Acute_Hosp_Readmsn_Rate\n"
    "State,CA,California,,06000,2023,6500000,50000000000.00,7692.31,14.5\n"
)

MODULE = "dk_data.ingestion.sources.cms_geographic_variation"


def test_loader_returns_success_result_shape():
    from dk_data.ingestion.sources.cms_geographic_variation import (
        load_cms_geographic_variation,
    )

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT.encode("utf-8"))
        path = f.name

    with patch(f"{MODULE}.get_cursor") as mock_gc, patch(
        f"{MODULE}.upsert_records"
    ) as mock_ur:
        mock_gc.return_value = _get_cursor_ctx(0)
        mock_ur.return_value = 1
        result = load_cms_geographic_variation(path)

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
    from dk_data.ingestion.sources.cms_geographic_variation import (
        load_cms_geographic_variation,
    )

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT.encode("utf-8"))
        path = f.name

    with patch(f"{MODULE}.get_cursor") as mock_gc:
        mock_gc.return_value = _get_cursor_ctx(1)
        result = load_cms_geographic_variation(path)

    assert result["status"] == "skipped"
    assert result["records_inserted"] == 0


def test_loader_does_not_call_log_to_meta():
    from dk_data.ingestion.sources.cms_geographic_variation import (
        load_cms_geographic_variation,
    )

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT.encode("utf-8"))
        path = f.name

    with patch(f"{MODULE}.get_cursor") as mock_gc, patch(
        f"{MODULE}.upsert_records"
    ) as mock_ur, patch(f"{MODULE}.log_to_meta", create=True) as mock_ltm:
        mock_gc.return_value = _get_cursor_ctx(0)
        mock_ur.return_value = 1
        load_cms_geographic_variation(path)
        mock_ltm.assert_not_called()


def test_fetcher_source_name():
    from dk_data.ingestion.fetchers.cms_geographic_variation import (
        CMSGeographicVariationFetcher,
    )

    assert CMSGeographicVariationFetcher.SOURCE_NAME == "cms_geographic_variation"
