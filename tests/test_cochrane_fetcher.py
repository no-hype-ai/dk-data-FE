"""Tests for Cochrane Fetcher (PubMed eUtils implementation).

Feature: 011-datasource-integration
Task: T064-T066 — Cochrane systematic reviews

Cochrane's own API is Cloudflare-blocked (#189). Fetcher now uses PubMed
eUtils (esearch + esummary) scoped to "Cochrane Database Syst Rev"[Journal].
"""

from datetime import date
from unittest.mock import patch

import pytest

from dk_data.ingestion.fetchers.cochrane import (
    ESEARCH_URL,
    CochraneFetcher,
)
from dk_data.ingestion.utils.validators import CochraneReviewRecord


# ---------------------------------------------------------------------------
# PubMed eSummary fixture — matches what NCBI returns
# ---------------------------------------------------------------------------

ESEARCH_RESPONSE = {
    "esearchresult": {
        "idlist": ["38000001", "38000002"],
        "count": "2",
    }
}

ESUMMARY_RESPONSE = {
    "result": {
        "38000001": {
            "uid": "38000001",
            "title": "Corticosteroids for COVID-19: a Cochrane review",
            "authors": [
                {"name": "Wagner C"},
                {"name": "Griesel M"},
            ],
            "pubdate": "2026 Mar 15",
            "epubdate": "",
            "articleids": [
                {"idtype": "doi", "value": "10.1002/14651858.CD013600.pub2"},
                {"idtype": "pubmed", "value": "38000001"},
            ],
        },
        "38000002": {
            "uid": "38000002",
            "title": "Antivirals for influenza: systematic review",
            "authors": [{"name": "Jefferson T"}],
            "pubdate": "2026 Jan",
            "epubdate": "",
            "articleids": [
                {"idtype": "doi", "value": "10.1002/14651858.CD008965.pub4"},
            ],
        },
    }
}

ESUMMARY_NO_DOI = {
    "result": {
        "38000003": {
            "uid": "38000003",
            "title": "No DOI review",
            "authors": [],
            "pubdate": "2026",
            "articleids": [],
        }
    }
}


# ---------------------------------------------------------------------------
# Fetcher tests: initialization
# ---------------------------------------------------------------------------

class TestCochraneFetcherInit:
    def test_fetcher_init(self, tmp_path):
        fetcher = CochraneFetcher(data_dir=str(tmp_path))
        assert fetcher.SOURCE_NAME == "cochrane"
        assert fetcher.session is not None
        assert fetcher.data_dir == tmp_path

    def test_fetcher_session_accepts_json(self, tmp_path):
        fetcher = CochraneFetcher(data_dir=str(tmp_path))
        assert fetcher.session.headers.get("Accept") == "application/json"


# ---------------------------------------------------------------------------
# Fetcher tests: get_latest_url
# ---------------------------------------------------------------------------

class TestCochraneFetcherURL:
    def test_get_latest_url(self, tmp_path):
        fetcher = CochraneFetcher(data_dir=str(tmp_path))
        url = fetcher.get_latest_url()
        assert "eutils.ncbi.nlm.nih.gov" in url
        assert url == ESEARCH_URL


# ---------------------------------------------------------------------------
# Fetcher tests: fetch with mocked PubMed HTTP
# ---------------------------------------------------------------------------

class TestCochraneFetcherFetch:

    def _make_fetch_json_side_effect(self, esearch_resp, esummary_resp):
        def _side_effect(url, params=None):
            if "esearch" in url:
                return esearch_resp
            return esummary_resp
        return _side_effect

    def test_fetch_success(self, tmp_path):
        fetcher = CochraneFetcher(data_dir=str(tmp_path))

        with patch.object(
            fetcher, "fetch_json",
            side_effect=self._make_fetch_json_side_effect(
                ESEARCH_RESPONSE, ESUMMARY_RESPONSE
            ),
        ):
            result = fetcher.fetch(search_terms=["corticosteroids"], days_back=90)

        assert result["status"] == "success"
        assert result["record_count"] == 2
        assert result["hash"] is not None
        titles = [r["title"] for r in result["records"]]
        assert "Corticosteroids for COVID-19: a Cochrane review" in titles

    def test_fetch_empty_results(self, tmp_path):
        fetcher = CochraneFetcher(data_dir=str(tmp_path))

        empty_search = {"esearchresult": {"idlist": [], "count": "0"}}
        with patch.object(fetcher, "fetch_json", return_value=empty_search):
            result = fetcher.fetch(search_terms=["nonexistent_drug_xyz"])

        assert result["status"] == "success"
        assert result["record_count"] == 0
        assert result["records"] == []

    def test_fetch_api_error(self, tmp_path):
        """Per-term esearch failures are caught inside _search_pmids and return [].
        The overall fetch degrades gracefully to success with 0 records rather
        than a hard failure — consistent with the platform's other fetchers.
        A hard status:failed is reserved for exceptions that escape the main loop.
        """
        fetcher = CochraneFetcher(data_dir=str(tmp_path))

        with patch.object(
            fetcher, "fetch_json",
            side_effect=Exception("Connection refused"),
        ):
            result = fetcher.fetch(search_terms=["test"])

        assert result["status"] == "success"
        assert result["record_count"] == 0
        assert result["records"] == []

    def test_fetch_returns_failed_on_unexpected_error(self, tmp_path):
        fetcher = CochraneFetcher(data_dir=str(tmp_path))

        with patch.object(
            fetcher, "_search_pmids",
            side_effect=RuntimeError("Unexpected internal error"),
        ):
            result = fetcher.fetch(search_terms=["test"])

        assert result["status"] == "failed"
        assert "Unexpected internal error" in result["error"]

    def test_fetch_deduplicates_records(self, tmp_path):
        """Same PMID from two different search terms produces only 1 record."""
        fetcher = CochraneFetcher(data_dir=str(tmp_path))

        single_hit_search = {"esearchresult": {"idlist": ["38000001"], "count": "1"}}
        single_hit_summary = {
            "result": {"38000001": ESUMMARY_RESPONSE["result"]["38000001"]}
        }

        def _side_effect(url, params=None):
            if "esearch" in url:
                return single_hit_search
            return single_hit_summary

        with patch.object(fetcher, "fetch_json", side_effect=_side_effect):
            result = fetcher.fetch(
                search_terms=["corticosteroids", "dexamethasone"],
            )

        assert result["status"] == "success"
        assert result["record_count"] == 1


# ---------------------------------------------------------------------------
# Fetcher tests: _normalize_summary
# ---------------------------------------------------------------------------

class TestCochraneNormalization:

    def test_normalize_full_record(self, tmp_path):
        import json
        fetcher = CochraneFetcher(data_dir=str(tmp_path))
        item = ESUMMARY_RESPONSE["result"]["38000001"]
        result = fetcher._normalize_summary(item, "corticosteroids")

        assert result is not None
        assert result["pmid"] == "38000001"
        assert result["review_id"] == "10.1002/14651858.CD013600.pub2"
        assert result["doi"] == "10.1002/14651858.CD013600.pub2"
        assert result["title"] == "Corticosteroids for COVID-19: a Cochrane review"
        # authors is a JSON array string for JSONB column compatibility
        authors = json.loads(result["authors"])
        assert "Wagner C" in authors
        assert result["review_type"] == "systematic_review"
        assert result["source"] == "pubmed_cochrane"
        assert result["search_term"] == "corticosteroids"

    def test_normalize_minimal_record_no_doi(self, tmp_path):
        fetcher = CochraneFetcher(data_dir=str(tmp_path))
        item = ESUMMARY_NO_DOI["result"]["38000003"]
        result = fetcher._normalize_summary(item, "test")

        assert result is not None
        assert result["pmid"] == "38000003"
        assert result["review_id"] == "pmid:38000003"
        assert result["doi"] is None
        assert result["authors"] is None

    def test_normalize_missing_uid_returns_none(self, tmp_path):
        fetcher = CochraneFetcher(data_dir=str(tmp_path))
        result = fetcher._normalize_summary({"title": "No UID"}, "test")
        assert result is None


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

class TestParsePubmedDate:

    @pytest.mark.parametrize("pubdate,expected", [
        ("2026 Mar 15", "2026-03-15"),
        ("2026 Mar",    "2026-03-01"),
        ("2026",        "2026-01-01"),
        ("2026-03-15",  "2026-03-15"),
        ("2026-03",     "2026-03-01"),
        ("",            None),
        ("Spring 2026", None),
    ])
    def test_parse_pubmed_date(self, pubdate, expected):
        result = CochraneFetcher._parse_pubmed_date(pubdate)
        assert result == expected


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------

class TestCochraneReviewRecordValid:

    def test_full_record(self):
        record = CochraneReviewRecord(
            review_id="10.1002/14651858.CD013600.pub2",
            title="Systemic corticosteroids for COVID-19",
            authors='["Wagner C", "Griesel M"]',
            abstract=None,
            publication_date=date(2026, 3, 15),
            review_type="systematic_review",
            interventions=None,
            conditions=None,
            conclusions=None,
            doi="10.1002/14651858.CD013600.pub2",
        )
        assert record.review_id == "10.1002/14651858.CD013600.pub2"
        assert record.publication_date == date(2026, 3, 15)

    def test_minimal_record(self):
        record = CochraneReviewRecord(review_id="pmid:38000001")
        assert record.review_id == "pmid:38000001"
        assert record.title is None
        assert record.authors is None


class TestCochraneReviewRecordInvalid:

    def test_empty_review_id(self):
        with pytest.raises(Exception):
            CochraneReviewRecord(review_id="")

    def test_missing_review_id(self):
        with pytest.raises(Exception):
            CochraneReviewRecord()

    def test_whitespace_only_review_id(self):
        with pytest.raises(Exception):
            CochraneReviewRecord(review_id="   ")
