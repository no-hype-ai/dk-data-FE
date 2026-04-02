"""Tests for cms_dual_eligible loader (019-cms-puf-platform-reconciliation T017)."""

from unittest.mock import MagicMock, patch


MODULE = "dk_data.ingestion.sources.cms_dual_eligible"

SAMPLE_RECORDS = [
    {
        "state_cd": "CA",
        "state_name": "California",
        "dual_elgbl_lvl": "FULL",
        "dual_elgbl_desc": "Full Dual",
        "tot_benes": 1500000,
        "ffs_benes": 600000,
        "ma_benes": 900000,
        "dual_elgbl_full_benes": 900000,
        "dual_elgbl_prtl_benes": 0,
        "non_dual_benes": 500000,
        "lis_benes": 100000,
    }
]


def test_loader_returns_success_result_shape():
    from dk_data.ingestion.sources.cms_dual_eligible import load_cms_dual_eligible_data

    with patch(f"{MODULE}.upsert_records", return_value=1):
        result = load_cms_dual_eligible_data(SAMPLE_RECORDS, source_hash="abc123")

    assert set(result.keys()) == {
        "status",
        "records_fetched",
        "records_inserted",
        "records_updated",
        "errors",
    }
    assert result["status"] == "success"
    assert result["records_fetched"] == 1
    assert result["records_inserted"] == 1


def test_loader_returns_success_for_empty_records():
    from dk_data.ingestion.sources.cms_dual_eligible import load_cms_dual_eligible_data

    result = load_cms_dual_eligible_data([])
    assert result["status"] == "success"
    assert result["records_fetched"] == 0
    assert result["records_inserted"] == 0


def test_loader_skips_on_duplicate_hash():
    from dk_data.ingestion.sources.cms_dual_eligible import load_cms_dual_eligible_data

    # ON CONFLICT DO UPDATE — upsert_records returns 0 when no change
    with patch(f"{MODULE}.upsert_records", return_value=0):
        result = load_cms_dual_eligible_data(SAMPLE_RECORDS)

    assert result["records_inserted"] == 0
    assert result["status"] == "success"


def test_loader_does_not_call_log_to_meta():
    from dk_data.ingestion.sources.cms_dual_eligible import load_cms_dual_eligible_data

    with patch(f"{MODULE}.upsert_records", return_value=1), \
         patch(f"{MODULE}.log_to_meta", create=True) as mock_ltm:
        load_cms_dual_eligible_data(SAMPLE_RECORDS)
        mock_ltm.assert_not_called()


def test_fetcher_source_name():
    from dk_data.ingestion.fetchers.cms_dual_eligible import CMSDualEligibleFetcher

    assert CMSDualEligibleFetcher.SOURCE_NAME == "cms_dual_eligible"
