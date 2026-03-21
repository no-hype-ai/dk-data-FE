"""Tests for HTA Bodies fetcher and validator with mocked HTTP.

Feature: 011-datasource-integration
Task: T058-T060 — HTA Bodies CI source integration

Tests use mocked HTTP responses so no external network calls are made.
"""

import tempfile
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from dk_data.ingestion.fetchers.hta_bodies import (
    AGENCIES,
    NICE_SEARCH_URL,
    HTABodiesFetcher,
)
from dk_data.ingestion.utils.validators import HTADecisionRecord


# ---------------------------------------------------------------------------
# NICE HTML fixtures for scraping tests
# ---------------------------------------------------------------------------

def _make_nice_search_html(ta_ids):
    """Build mock NICE search results HTML containing guidance links."""
    links = "\n".join(
        f'<a href="/guidance/{ta_id}">{ta_id}</a>' for ta_id in ta_ids
    )
    return f"<html><body>{links}</body></html>"


def _make_nice_ta_page_html(ta_id, title, date_str, recommendation_text):
    """Build mock NICE TA recommendation page HTML."""
    return f"""<html><body>
    <h1>{title}</h1>
    <time datetime="{date_str}">Published</time>
    <div>1.1 {recommendation_text} 1.2 Next section</div>
    </body></html>"""


# ---------------------------------------------------------------------------
# Fetcher initialisation tests
# ---------------------------------------------------------------------------

class TestHTABodiesFetcherInit:
    """Tests for fetcher initialization."""

    def test_fetcher_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = HTABodiesFetcher(data_dir=tmpdir)
            assert fetcher.SOURCE_NAME == "hta_bodies"
            assert fetcher.session is not None

    def test_fetcher_init_defaults(self):
        fetcher = HTABodiesFetcher()
        assert fetcher.SOURCE_NAME == "hta_bodies"
        assert fetcher.data_dir.exists()

    def test_get_latest_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = HTABodiesFetcher(data_dir=tmpdir)
            url = fetcher.get_latest_url()
            assert url == NICE_SEARCH_URL
            assert "nice.org.uk" in url


# ---------------------------------------------------------------------------
# Fetch with mocked HTTP
# ---------------------------------------------------------------------------

class TestHTABodiesFetch:
    """Tests for the fetch method with mocked HTTP responses."""

    def test_fetch_nice_success(self, tmp_path):
        """NICE scraping returns guidance items."""
        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        search_html = _make_nice_search_html(["ta900", "ta901"])
        ta900_html = _make_nice_ta_page_html(
            "TA900",
            "Pembrolizumab for advanced melanoma",
            "2026-02-05",
            "Pembrolizumab is recommended for treating advanced melanoma in adults.",
        )
        ta901_html = _make_nice_ta_page_html(
            "TA901",
            "Nivolumab for lung cancer",
            "2026-02-10",
            "Nivolumab is recommended for treating non-small-cell lung cancer.",
        )

        def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            if "Search" in url:
                resp.text = search_html
            elif "ta900" in url:
                resp.text = ta900_html
            elif "ta901" in url:
                resp.text = ta901_html
            else:
                resp.text = search_html
            return resp

        with patch("dk_data.ingestion.fetchers.hta_bodies.requests.get", side_effect=mock_get):
            with patch("dk_data.ingestion.fetchers.hta_bodies.time.sleep"):
                result = fetcher.fetch(
                    drug_names=["pembrolizumab", "nivolumab"],
                    agencies=["nice"],
                    days_back=90,
                )

        assert result["status"] == "success"
        assert len(result["records"]) == 2
        assert result["hash"] is not None

        rec = result["records"][0]
        assert rec["decision_id"] == "nice-TA900"
        assert rec["agency"] == "nice"
        assert rec["decision_type"] == "Recommended"

    def test_fetch_nice_empty_response(self, tmp_path):
        """NICE search returns no TA links."""
        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        mock_response = MagicMock()
        mock_response.text = "<html><body>No results found</body></html>"
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("dk_data.ingestion.fetchers.hta_bodies.requests.get", return_value=mock_response):
            with patch("dk_data.ingestion.fetchers.hta_bodies.time.sleep"):
                result = fetcher.fetch(
                    drug_names=["nonexistent_drug"],
                    agencies=["nice"],
                )

        assert result["status"] == "success"
        assert result["records"] == []

    def test_fetch_nice_network_error_handled(self, tmp_path):
        """NICE network error is handled gracefully."""
        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        with patch(
            "dk_data.ingestion.fetchers.hta_bodies.requests.get",
            side_effect=Exception("Connection refused"),
        ):
            result = fetcher.fetch(
                drug_names=["pembrolizumab"],
                agencies=["nice"],
            )

        assert result["status"] == "success"
        assert result["records"] == []

    def test_fetch_stub_agencies_return_empty(self, tmp_path):
        """Stub agencies (gba, has, pbac) return empty results."""
        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        result = fetcher.fetch(
            drug_names=["pembrolizumab"],
            agencies=["gba", "has", "pbac"],
        )

        assert result["status"] == "success"
        assert result["records"] == []

    def test_fetch_all_agencies(self, tmp_path):
        """Fetch across all agencies (NICE + others)."""
        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        search_html = _make_nice_search_html(["ta900"])
        ta_html = _make_nice_ta_page_html(
            "TA900",
            "Pembrolizumab for melanoma",
            "2026-02-05",
            "Pembrolizumab is recommended for treating advanced melanoma.",
        )

        def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            if "Search" in url:
                resp.text = search_html
            elif "ta900" in url:
                resp.text = ta_html
            else:
                resp.text = "<html></html>"
            return resp

        with patch("dk_data.ingestion.fetchers.hta_bodies.requests.get", side_effect=mock_get):
            with patch("dk_data.ingestion.fetchers.hta_bodies.time.sleep"):
                result = fetcher.fetch(
                    drug_names=["pembrolizumab"],
                    agencies=AGENCIES,
                    days_back=90,
                )

        assert result["status"] == "success"
        assert any(r["agency"] == "nice" for r in result["records"])

    def test_fetch_deduplication_across_agencies(self, tmp_path):
        """Decisions with the same ID are deduplicated."""
        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        with patch.object(
            fetcher,
            "_fetch_agency",
            side_effect=[
                [{"decision_id": "nice-TA900", "agency": "nice", "drug_name": "Test"}],
                [{"decision_id": "nice-TA900", "agency": "nice", "drug_name": "Test"}],
            ],
        ):
            result = fetcher.fetch(
                drug_names=["test"],
                agencies=["nice", "nice"],
            )

        assert result["status"] == "success"
        assert len(result["records"]) == 1


# ---------------------------------------------------------------------------
# NICE item normalisation tests
# ---------------------------------------------------------------------------

class TestNICEDecisionClassification:
    """Tests for NICE decision classification and indication extraction."""

    def test_classify_recommended(self):
        fetcher = HTABodiesFetcher()
        assert fetcher._classify_nice_decision(
            "Pembrolizumab is recommended for treating advanced melanoma"
        ) == "Recommended"

    def test_classify_not_recommended(self):
        fetcher = HTABodiesFetcher()
        assert fetcher._classify_nice_decision(
            "Drug X is not recommended for use"
        ) == "Not recommended"

    def test_classify_cdf(self):
        fetcher = HTABodiesFetcher()
        assert fetcher._classify_nice_decision(
            "Drug X is recommended for use within the Cancer Drugs Fund"
        ) == "Recommended (CDF)"

    def test_classify_conditional(self):
        fetcher = HTABodiesFetcher()
        assert fetcher._classify_nice_decision(
            "Drug X can be used for treating condition Y"
        ) == "Recommended (conditional)"

    def test_classify_unknown_text(self):
        fetcher = HTABodiesFetcher()
        assert fetcher._classify_nice_decision(
            "Some unrelated text about a drug"
        ) == "Unknown"

    def test_classify_empty_text(self):
        fetcher = HTABodiesFetcher()
        assert fetcher._classify_nice_decision("") is None

    def test_extract_indication_for_treating(self):
        result = HTABodiesFetcher._extract_nice_indication(
            "Pembrolizumab is recommended for treating advanced melanoma in adults."
        )
        assert result == "advanced melanoma"

    def test_extract_indication_cancer(self):
        result = HTABodiesFetcher._extract_nice_indication(
            "Nivolumab for treating metastatic non-small-cell lung cancer"
        )
        assert "lung cancer" in result

    def test_extract_indication_none(self):
        result = HTABodiesFetcher._extract_nice_indication(
            "Some text with no clear indication pattern"
        )
        assert result is None


# ---------------------------------------------------------------------------
# HTADecisionRecord validator tests
# ---------------------------------------------------------------------------

class TestHTADecisionRecord:
    """Tests for the HTADecisionRecord Pydantic model."""

    def test_valid_record(self):
        record = HTADecisionRecord(
            decision_id="nice-TA900",
            agency="nice",
            drug_name="Pembrolizumab",
            indication="Advanced melanoma",
            decision_type="Recommended",
            decision_date=date(2026, 2, 5),
            document_url="https://www.nice.org.uk/guidance/ta900",
            summary="Recommended for treating advanced melanoma.",
        )
        assert record.decision_id == "nice-TA900"
        assert record.agency == "nice"
        assert record.drug_name == "Pembrolizumab"

    def test_minimal_record(self):
        record = HTADecisionRecord(
            decision_id="nice-TA001",
            agency="nice",
        )
        assert record.decision_id == "nice-TA001"
        assert record.drug_name is None
        assert record.indication is None

    def test_all_valid_agencies(self):
        for agency in HTADecisionRecord.VALID_AGENCIES:
            record = HTADecisionRecord(
                decision_id=f"{agency}-001",
                agency=agency,
            )
            assert record.agency == agency

    def test_invalid_agency_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            HTADecisionRecord(
                decision_id="fda-001",
                agency="fda",
            )
        assert "agency" in str(exc_info.value).lower()

    def test_empty_decision_id_rejected(self):
        with pytest.raises(ValidationError):
            HTADecisionRecord(decision_id="", agency="nice")

    def test_missing_decision_id_rejected(self):
        with pytest.raises(ValidationError):
            HTADecisionRecord(agency="nice")

    def test_empty_agency_rejected(self):
        with pytest.raises(ValidationError):
            HTADecisionRecord(decision_id="nice-001", agency="")

    def test_agency_case_insensitive(self):
        record = HTADecisionRecord(
            decision_id="nice-001",
            agency="NICE",
        )
        assert record.agency == "nice"

    def test_whitespace_stripped(self):
        record = HTADecisionRecord(
            decision_id="  nice-001  ",
            agency="  nice  ",
        )
        assert record.decision_id == "nice-001"
        assert record.agency == "nice"
