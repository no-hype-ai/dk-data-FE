"""Tests for cms_medicaid_drug_spending loader (019-cms-puf-platform-reconciliation T017)."""

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
    "Drug Name,State,Labeler Code,Product Code,Package Size,NDC,"
    "Units Reimbursed,Number of Prescriptions,Total Amount Reimbursed,"
    "Medicaid Amount Reimbursed,Non Medicaid Amount Reimbursed,Quarter\n"
    "METFORMIN HCL,CA,00093,1234,01,000931234001,"
    "10000.0,500,25000.00,20000.00,5000.00,1\n"
)

MODULE = "dk_data.ingestion.sources.cms_medicaid_drug_spending"


def test_loader_returns_success_result_shape():
    from dk_data.ingestion.sources.cms_medicaid_drug_spending import (
        load_cms_medicaid_drug_spending,
    )

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT.encode("utf-8"))
        path = f.name

    with patch(f"{MODULE}.get_cursor") as mock_gc, patch(
        f"{MODULE}.upsert_records"
    ) as mock_ur:
        mock_gc.return_value = _get_cursor_ctx(0)
        mock_ur.return_value = 1
        result = load_cms_medicaid_drug_spending(path)

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
    from dk_data.ingestion.sources.cms_medicaid_drug_spending import (
        load_cms_medicaid_drug_spending,
    )

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT.encode("utf-8"))
        path = f.name

    with patch(f"{MODULE}.get_cursor") as mock_gc:
        mock_gc.return_value = _get_cursor_ctx(1)
        result = load_cms_medicaid_drug_spending(path)

    assert result["status"] == "skipped"
    assert result["records_inserted"] == 0


def test_loader_does_not_call_log_to_meta():
    from dk_data.ingestion.sources.cms_medicaid_drug_spending import (
        load_cms_medicaid_drug_spending,
    )

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT.encode("utf-8"))
        path = f.name

    with patch(f"{MODULE}.get_cursor") as mock_gc, patch(
        f"{MODULE}.upsert_records"
    ) as mock_ur, patch(f"{MODULE}.log_to_meta", create=True) as mock_ltm:
        mock_gc.return_value = _get_cursor_ctx(0)
        mock_ur.return_value = 1
        load_cms_medicaid_drug_spending(path)
        mock_ltm.assert_not_called()


def test_fetcher_source_name():
    from dk_data.ingestion.fetchers.cms_medicaid_drug_spending import (
        CMSMedicaidDrugSpendingFetcher,
    )

    assert CMSMedicaidDrugSpendingFetcher.SOURCE_NAME == "cms_medicaid_drug_spending"
