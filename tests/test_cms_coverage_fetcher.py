"""Tests for CMSCoverageFetcher."""

from unittest.mock import patch

import pytest
import responses as resp_lib

from dk_data.ingestion.fetchers.cms_coverage import CMSCoverageFetcher


@pytest.fixture
def fetcher():
    return CMSCoverageFetcher()


def _make_page(records, total=None):
    """Helper: wrap records in the API envelope format."""
    return {"data": records, "meta": {"total": total or len(records)}}


class TestGetLatestUrl:
    def test_returns_ncd_url(self, fetcher):
        assert fetcher.get_latest_url() == "https://api.coverage.cms.gov/v1/data/ncd/"


class TestFetchSuccess:
    @resp_lib.activate
    def test_fetch_returns_records_from_all_endpoints(self, fetcher):
        ncd_record = {"id": "ncd-1", "title": "NCD 1"}
        nca_record = {"id": "nca-1", "title": "NCA 1"}
        ta_record = {"id": "ta-1", "title": "TA 1"}

        resp_lib.add(
            resp_lib.GET,
            "https://api.coverage.cms.gov/v1/data/ncd/",
            json=_make_page([ncd_record]),
            status=200,
        )
        resp_lib.add(
            resp_lib.GET,
            "https://api.coverage.cms.gov/v1/data/nca/",
            json=_make_page([nca_record]),
            status=200,
        )
        resp_lib.add(
            resp_lib.GET,
            "https://api.coverage.cms.gov/v1/data/technology-assessment/",
            json=_make_page([ta_record]),
            status=200,
        )

        result = fetcher.fetch()

        assert result["status"] == "success"
        assert result["record_count"] == 3
        records = result["records"]
        endpoints = {r["_endpoint"] for r in records}
        assert endpoints == {"ncd", "nca", "technology_assessment"}

    @resp_lib.activate
    def test_fetch_tags_endpoint_field(self, fetcher):
        resp_lib.add(
            resp_lib.GET,
            "https://api.coverage.cms.gov/v1/data/ncd/",
            json=_make_page([{"id": "1", "title": "Test NCD"}]),
            status=200,
        )
        resp_lib.add(
            resp_lib.GET,
            "https://api.coverage.cms.gov/v1/data/nca/",
            json=_make_page([]),
            status=200,
        )
        resp_lib.add(
            resp_lib.GET,
            "https://api.coverage.cms.gov/v1/data/technology-assessment/",
            json=_make_page([]),
            status=200,
        )

        result = fetcher.fetch()
        ncd_records = [r for r in result["records"] if r["_endpoint"] == "ncd"]
        assert len(ncd_records) == 1
        assert ncd_records[0]["id"] == "1"

    @resp_lib.activate
    def test_fetch_deduplicates_by_id_endpoint(self, fetcher):
        """Duplicate (id, endpoint) records are collapsed to one."""
        record = {"id": "dup-1", "title": "Duplicate"}
        resp_lib.add(
            resp_lib.GET,
            "https://api.coverage.cms.gov/v1/data/ncd/",
            json={"data": [record, record], "meta": {"total": 2}},
            status=200,
        )
        resp_lib.add(
            resp_lib.GET,
            "https://api.coverage.cms.gov/v1/data/nca/",
            json=_make_page([]),
            status=200,
        )
        resp_lib.add(
            resp_lib.GET,
            "https://api.coverage.cms.gov/v1/data/technology-assessment/",
            json=_make_page([]),
            status=200,
        )

        result = fetcher.fetch()
        assert result["record_count"] == 1

    @resp_lib.activate
    def test_fetch_returns_hash(self, fetcher):
        resp_lib.add(
            resp_lib.GET,
            "https://api.coverage.cms.gov/v1/data/ncd/",
            json=_make_page([{"id": "x", "title": "X"}]),
            status=200,
        )
        resp_lib.add(
            resp_lib.GET,
            "https://api.coverage.cms.gov/v1/data/nca/",
            json=_make_page([]),
            status=200,
        )
        resp_lib.add(
            resp_lib.GET,
            "https://api.coverage.cms.gov/v1/data/technology-assessment/",
            json=_make_page([]),
            status=200,
        )

        result = fetcher.fetch()
        assert result["hash"] is not None
        assert len(result["hash"]) == 32  # MD5 hex


class TestFetchError:
    @resp_lib.activate
    def test_fetch_returns_success_with_zero_records_on_all_endpoint_errors(self, fetcher):
        """Per-endpoint errors are caught; all failing → success with 0 records."""
        for path in ["/data/ncd/", "/data/nca/", "/data/technology-assessment/"]:
            resp_lib.add(
                resp_lib.GET,
                f"https://api.coverage.cms.gov/v1{path}",
                body=Exception("Connection refused"),
            )

        result = fetcher.fetch()
        assert result["status"] == "success"
        assert result["records"] == []
        assert result["record_count"] == 0

    def test_fetch_returns_failed_on_unexpected_top_level_error(self, fetcher):
        """An unexpected error in _fetch_all_endpoints propagates as failed."""
        with patch.object(fetcher, "_fetch_all_endpoints", side_effect=RuntimeError("crash")):
            result = fetcher.fetch()
        assert result["status"] == "failed"
        assert result["records"] == []

    @resp_lib.activate
    def test_fetch_skips_404_endpoint(self, fetcher):
        """A 404 on one endpoint should not fail the entire fetch."""
        resp_lib.add(
            resp_lib.GET,
            "https://api.coverage.cms.gov/v1/data/ncd/",
            json=_make_page([{"id": "1", "title": "NCD 1"}]),
            status=200,
        )
        resp_lib.add(
            resp_lib.GET,
            "https://api.coverage.cms.gov/v1/data/nca/",
            status=404,
        )
        resp_lib.add(
            resp_lib.GET,
            "https://api.coverage.cms.gov/v1/data/technology-assessment/",
            json=_make_page([]),
            status=200,
        )

        result = fetcher.fetch()
        assert result["status"] == "success"
        assert result["record_count"] == 1


class TestExtractRecords:
    def test_plain_list(self):
        data = [{"id": "1"}, {"id": "2"}]
        records, total = CMSCoverageFetcher._extract_records(data)
        assert records == data
        assert total == 2

    def test_data_key_with_meta_total(self):
        data = {"data": [{"id": "a"}], "meta": {"total": 50}}
        records, total = CMSCoverageFetcher._extract_records(data)
        assert records == [{"id": "a"}]
        assert total == 50

    def test_results_key_with_count(self):
        data = {"results": [{"id": "b"}], "count": 10}
        records, total = CMSCoverageFetcher._extract_records(data)
        assert records == [{"id": "b"}]
        assert total == 10

    def test_unknown_shape_returns_empty(self):
        data = {"unexpected": "format"}
        records, total = CMSCoverageFetcher._extract_records(data)
        assert records == []
        assert total is None

    def test_none_total_when_meta_absent(self):
        data = {"data": [{"id": "c"}]}
        records, total = CMSCoverageFetcher._extract_records(data)
        assert records == [{"id": "c"}]
        assert total is None
