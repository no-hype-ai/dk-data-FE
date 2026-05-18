"""Tests for the TAVR catalog (data.gov) fetcher with mocked HTTP.

Covers the 2026 migration off the retired CKAN Action API
(`/api/3/action/package_search`, now HTTP 404) onto the live
`https://catalog.data.gov/search` Catalog Search API.

The downstream silver/gold loader (`sources/tavr_catalog_data_gov.py`)
parses `rec["_package"]` with CKAN keys and must stay byte-compatible, so
these tests assert the fetcher normalizes each new-API record into a
CKAN-compatible `pkg` dict. No external network calls are made — the
inherited `fetch_json` is patched.

Feature: 006-tavr-catalog-candidate-manifest-provisioning
"""

from unittest.mock import patch

from dk_data.ingestion.fetchers.tavr_catalog_data_gov import (
    DEFAULT_CATALOG_SEARCH_URL,
    TavrCatalogDataGovFetcher,
    _normalize_to_ckan_pkg,
)


# ---------------------------------------------------------------------------
# Sample new-API (Catalog Search) payload fixtures
# ---------------------------------------------------------------------------

def _search_record(
    identifier="11111111-1111-1111-1111-111111111111",
    slug="medicare-tavr-outcomes",
    title="Medicare TAVR Outcomes",
):
    """A single record in the new `https://catalog.data.gov/search` shape."""
    return {
        "identifier": identifier,
        "slug": slug,
        "title": title,
        "description": "Transcatheter aortic valve replacement outcomes by hospital.",
        "keyword": ["tavr", "medicare", "cardiac"],
        "organization": {"name": "Centers for Medicare & Medicaid Services"},
        "theme": ["Health"],
        "publisher": "CMS",
        "distribution_titles": ["CSV download"],
        "dcat": {
            "title": "Medicare TAVR Outcomes (DCAT)",
            "description": "DCAT description.",
            "license": "https://creativecommons.org/publicdomain/zero/1.0/",
            "temporal": "2010-01-01/2020-12-31",
            "distribution": [
                {
                    "downloadURL": "https://data.cms.gov/tavr-outcomes.csv",
                    "format": "CSV",
                    "mediaType": "text/csv",
                    "title": "TAVR Outcomes CSV",
                    "byteSize": 204800,
                },
                {
                    # accessURL fallback (no downloadURL)
                    "accessURL": "https://data.cms.gov/tavr-api",
                    "mediaType": "application/json",
                    "title": "TAVR API",
                },
                {
                    # No url at all — must be skipped (mirrors loader behaviour)
                    "format": "PDF",
                    "title": "No URL distribution",
                },
            ],
        },
    }


def _search_payload(records=None):
    """Top-level new-API envelope: {"results": [...], "after": "<cursor>"}."""
    if records is None:
        records = [_search_record()]
    return {"results": records, "after": "cursor-abc"}


# ---------------------------------------------------------------------------
# Tests: fetcher init / URL resolution
# ---------------------------------------------------------------------------

class TestFetcherInit:
    def test_source_name_and_base_url(self):
        fetcher = TavrCatalogDataGovFetcher()
        assert fetcher.SOURCE_NAME == "tavr_catalog_data_gov"
        # No longer the retired CKAN Action API.
        assert "/api/3/action/package_search" not in fetcher.BASE_URL
        assert fetcher.BASE_URL == DEFAULT_CATALOG_SEARCH_URL
        assert DEFAULT_CATALOG_SEARCH_URL == "https://catalog.data.gov/search"

    def test_get_latest_url_default(self):
        fetcher = TavrCatalogDataGovFetcher()
        assert fetcher.get_latest_url() == "https://catalog.data.gov/search"

    def test_get_latest_url_env_override(self, monkeypatch):
        monkeypatch.setenv(
            "DATA_GOV_CATALOG_SEARCH_URL", "https://api.data.gov/catalog/search"
        )
        fetcher = TavrCatalogDataGovFetcher()
        assert fetcher.get_latest_url() == "https://api.data.gov/catalog/search"


# ---------------------------------------------------------------------------
# Tests: normalization mapping (new API record -> CKAN-compatible pkg)
# ---------------------------------------------------------------------------

class TestNormalizeToCkanPkg:
    def test_core_field_mapping(self):
        pkg = _normalize_to_ckan_pkg(_search_record())
        assert pkg["id"] == "11111111-1111-1111-1111-111111111111"
        assert pkg["name"] == "medicare-tavr-outcomes"
        assert pkg["title"] == "Medicare TAVR Outcomes"
        # license string/URL from dcat.license; license_title absent.
        assert pkg["license_id"] == (
            "https://creativecommons.org/publicdomain/zero/1.0/"
        )
        assert "license_title" not in pkg
        assert pkg["temporal"] == "2010-01-01/2020-12-31"
        assert pkg["data_dictionary_url"] is None

    def test_title_falls_back_to_dcat_title(self):
        rec = _search_record()
        rec["title"] = None
        pkg = _normalize_to_ckan_pkg(rec)
        assert pkg["title"] == "Medicare TAVR Outcomes (DCAT)"

    def test_resources_mapping_and_url_skip(self):
        pkg = _normalize_to_ckan_pkg(_search_record())
        resources = pkg["resources"]
        # Third distribution has no url -> skipped.
        assert len(resources) == 2
        first = resources[0]
        assert first["url"] == "https://data.cms.gov/tavr-outcomes.csv"
        assert first["format"] == "CSV"
        assert first["name"] == "TAVR Outcomes CSV"
        assert first["size"] == 204800
        # Second uses accessURL + mediaType fallbacks.
        second = resources[1]
        assert second["url"] == "https://data.cms.gov/tavr-api"
        assert second["format"] == "application/json"

    def test_forward_compat_extras_and_raw_preserved(self):
        rec = _search_record()
        pkg = _normalize_to_ckan_pkg(rec)
        assert pkg["notes"] == (
            "Transcatheter aortic valve replacement outcomes by hospital."
        )
        assert pkg["tags"] == [
            {"name": "tavr"},
            {"name": "medicare"},
            {"name": "cardiac"},
        ]
        # Full original record retained for future silver work.
        assert pkg["_data_gov_raw"] == rec

    def test_missing_dcat_is_tolerated(self):
        rec = {"identifier": "abc", "slug": "no-dcat", "title": "No DCAT"}
        pkg = _normalize_to_ckan_pkg(rec)
        assert pkg["id"] == "abc"
        assert pkg["resources"] == []
        assert pkg["license_id"] is None
        assert pkg["temporal"] is None
        assert pkg["tags"] == []


# ---------------------------------------------------------------------------
# Tests: fetch() with mocked fetch_json — happy path
# ---------------------------------------------------------------------------

class TestFetchHappyPath:
    def test_fetch_uses_search_url_and_per_page_param(self):
        fetcher = TavrCatalogDataGovFetcher()
        with patch.object(
            fetcher, "fetch_json", return_value=_search_payload()
        ) as mock_json:
            result = fetcher.fetch(queries=["tavr"], rows_per_query=2)

        assert result["status"] == "success"
        assert result["record_count"] == 1
        # Endpoint + params migrated: search URL, per_page (not rows).
        called_url, called_kwargs = mock_json.call_args[0][0], mock_json.call_args[1]
        assert called_url == "https://catalog.data.gov/search"
        assert called_kwargs["params"] == {"q": "tavr", "per_page": 2}

    def test_fetch_record_has_ckan_compatible_package(self):
        fetcher = TavrCatalogDataGovFetcher()
        with patch.object(fetcher, "fetch_json", return_value=_search_payload()):
            result = fetcher.fetch(queries=["tavr"])

        assert len(result["records"]) == 1
        rec = result["records"][0]
        assert rec["_search_query"] == "tavr"
        pkg = rec["_package"]
        # The unchanged loader reads exactly these keys.
        assert pkg["id"] == "11111111-1111-1111-1111-111111111111"
        assert pkg["name"] == "medicare-tavr-outcomes"
        assert pkg["title"] == "Medicare TAVR Outcomes"
        assert pkg["license_id"].startswith("https://creativecommons.org")
        assert pkg["resources"][0]["url"].endswith(".csv")

    def test_fetch_dedups_by_identifier_across_queries(self):
        fetcher = TavrCatalogDataGovFetcher()
        # Same identifier returned for two different queries -> one record.
        with patch.object(
            fetcher, "fetch_json", return_value=_search_payload()
        ):
            result = fetcher.fetch(queries=["tavr", "aortic stenosis"])
        assert result["record_count"] == 1

    def test_fetch_respects_max_records(self):
        fetcher = TavrCatalogDataGovFetcher()
        recs = [
            _search_record(identifier=f"id-{i}", slug=f"slug-{i}")
            for i in range(5)
        ]
        with patch.object(
            fetcher, "fetch_json", return_value=_search_payload(recs)
        ):
            result = fetcher.fetch(queries=["tavr"], max_records=3)
        assert result["record_count"] == 3


# ---------------------------------------------------------------------------
# Tests: fetch() — empty / error handling
# ---------------------------------------------------------------------------

class TestFetchEdgeCases:
    def test_empty_results_skipped(self):
        fetcher = TavrCatalogDataGovFetcher()
        with patch.object(
            fetcher, "fetch_json", return_value={"results": [], "after": None}
        ):
            result = fetcher.fetch(queries=["tavr"])
        assert result["status"] == "success"
        assert result["record_count"] == 0

    def test_no_results_key_is_tolerated(self):
        # The retired CKAN API wrapped data under "result"; the new API does
        # not. A payload without "results" must yield zero records, not crash.
        fetcher = TavrCatalogDataGovFetcher()
        with patch.object(fetcher, "fetch_json", return_value={"help": "..."}):
            result = fetcher.fetch(queries=["tavr"])
        assert result["status"] == "success"
        assert result["record_count"] == 0

    def test_fetch_exception_returns_failed_envelope(self):
        fetcher = TavrCatalogDataGovFetcher()
        with patch.object(
            fetcher, "fetch_json", side_effect=RuntimeError("HTTP 404")
        ):
            result = fetcher.fetch(queries=["tavr"])
        assert result["status"] == "failed"
        assert result["record_count"] == 0
        assert result["hash"] is None
        assert "HTTP 404" in result["error"]
