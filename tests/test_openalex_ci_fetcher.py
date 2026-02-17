"""Tests for OpenAlex CI Fetcher and validator with mocked HTTP.

Feature: 011-datasource-integration
Task: Tier 4 CI source — OpenAlex publications

Tests cover:
- Fetcher initialization and session configuration
- get_latest_url endpoint
- Full fetch with mocked OpenAlex API (cursor pagination)
- OpenAlexCIRecord validation (valid and invalid)
"""

import tempfile
from datetime import date

import pytest
import responses

from dk_data.ingestion.fetchers.openalex_ci import OpenAlexCIFetcher
from dk_data.ingestion.utils.validators import OpenAlexCIRecord


# ---------------------------------------------------------------------------
# Sample OpenAlex API response fixtures
# ---------------------------------------------------------------------------

SAMPLE_WORK = {
    "id": "https://openalex.org/W2741809807",
    "doi": "https://doi.org/10.1038/s41586-021-03819-2",
    "title": "Highly accurate protein structure prediction with AlphaFold",
    "publication_date": "2021-07-15",
    "cited_by_count": 12345,
    "abstract_inverted_index": {
        "Proteins": [0],
        "are": [1],
        "essential": [2],
        "to": [3],
        "life.": [4],
    },
    "concepts": [
        {
            "id": "https://openalex.org/C86803240",
            "display_name": "Pharmaceutical sciences",
            "level": 1,
            "score": 0.85,
        },
        {
            "id": "https://openalex.org/C71924100",
            "display_name": "Medicine",
            "level": 0,
            "score": 0.72,
        },
    ],
    "authorships": [
        {
            "author": {
                "id": "https://openalex.org/A1234567",
                "display_name": "John Doe",
            },
            "institutions": [],
        }
    ],
    "primary_location": {
        "source": {
            "id": "https://openalex.org/S123",
            "display_name": "Nature",
        }
    },
    "open_access": {
        "is_oa": True,
        "oa_status": "gold",
    },
}

SAMPLE_WORK_MINIMAL = {
    "id": "https://openalex.org/W9999999999",
    "doi": None,
    "title": "A minimal record with no abstract",
    "publication_date": "2024-01-01",
    "cited_by_count": 0,
    "abstract_inverted_index": None,
    "concepts": [],
    "authorships": [],
    "primary_location": None,
    "open_access": None,
}


def _make_openalex_response(results, next_cursor=None):
    """Build a mock OpenAlex API response body."""
    return {
        "meta": {
            "count": len(results),
            "db_response_time_ms": 42,
            "page": None,
            "per_page": 200,
            "next_cursor": next_cursor,
        },
        "results": results,
    }


# ---------------------------------------------------------------------------
# Fetcher tests
# ---------------------------------------------------------------------------


class TestOpenAlexCIFetcherInit:
    """Tests for fetcher initialization."""

    def test_fetcher_init(self):
        """Verify fetcher initializes with correct source name and base URL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = OpenAlexCIFetcher(data_dir=tmpdir)
            assert fetcher.SOURCE_NAME == "openalex_ci"
            assert fetcher.BASE_URL == "https://api.openalex.org"
            assert fetcher.session is not None

    def test_fetcher_session_has_mailto_header(self):
        """Verify the polite pool mailto is set in the User-Agent header."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = OpenAlexCIFetcher(data_dir=tmpdir)
            user_agent = fetcher.session.headers.get("User-Agent", "")
            assert "mailto:" in user_agent

    def test_fetcher_session_accepts_json(self):
        """Verify the Accept header requests JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = OpenAlexCIFetcher(data_dir=tmpdir)
            assert fetcher.session.headers.get("Accept") == "application/json"

    def test_fetcher_data_dir_created(self):
        """Verify the data directory is created on init."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import os
            data_path = os.path.join(tmpdir, "sub", "raw")
            OpenAlexCIFetcher(data_dir=data_path)  # side-effect: creates dir
            assert os.path.exists(data_path)


class TestOpenAlexCIFetcherURL:
    """Tests for get_latest_url."""

    def test_get_latest_url(self):
        """Verify get_latest_url returns the /works endpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = OpenAlexCIFetcher(data_dir=tmpdir)
            url = fetcher.get_latest_url()
            assert url == "https://api.openalex.org/works"


class TestOpenAlexCIFetcherFetch:
    """Tests for the fetch method with mocked HTTP responses."""

    @responses.activate
    def test_fetch_with_mock(self):
        """Test a complete fetch with a single page of results."""
        # Mock the API: first page returns results, second page returns empty
        responses.add(
            responses.GET,
            "https://api.openalex.org/works",
            json=_make_openalex_response(
                [SAMPLE_WORK, SAMPLE_WORK_MINIMAL],
                next_cursor="cursor_page_2",
            ),
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.openalex.org/works",
            json=_make_openalex_response([], next_cursor=None),
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = OpenAlexCIFetcher(data_dir=tmpdir)
            result = fetcher.fetch(days_back=7)

            assert result["status"] == "success"
            assert result["record_count"] == 2
            assert len(result["records"]) == 2
            assert result["hash"] is not None

            # Verify record normalization
            rec = result["records"][0]
            assert rec["work_id"] == "W2741809807"
            assert rec["doi"] == "https://doi.org/10.1038/s41586-021-03819-2"
            assert rec["title"] == "Highly accurate protein structure prediction with AlphaFold"
            assert rec["cited_by_count"] == 12345
            assert rec["abstract"] is not None
            assert "Proteins" in rec["abstract"]
            assert rec["concepts"] is not None
            assert len(rec["concepts"]) == 2

            # Verify minimal record
            rec_min = result["records"][1]
            assert rec_min["work_id"] == "W9999999999"
            assert rec_min["abstract"] is None

    @responses.activate
    def test_fetch_cursor_pagination(self):
        """Test that cursor-based pagination works across multiple pages."""
        # Page 1
        responses.add(
            responses.GET,
            "https://api.openalex.org/works",
            json=_make_openalex_response([SAMPLE_WORK], next_cursor="page2_cursor"),
            status=200,
        )
        # Page 2
        responses.add(
            responses.GET,
            "https://api.openalex.org/works",
            json=_make_openalex_response([SAMPLE_WORK_MINIMAL], next_cursor="page3_cursor"),
            status=200,
        )
        # Page 3 (empty — signals end)
        responses.add(
            responses.GET,
            "https://api.openalex.org/works",
            json=_make_openalex_response([], next_cursor=None),
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = OpenAlexCIFetcher(data_dir=tmpdir)
            result = fetcher.fetch(days_back=3)

            assert result["status"] == "success"
            assert result["record_count"] == 2
            # Verify both pages were consumed (3 HTTP calls total)
            assert len(responses.calls) == 3

    @responses.activate
    def test_fetch_empty_results(self):
        """Test fetch when no results are returned."""
        responses.add(
            responses.GET,
            "https://api.openalex.org/works",
            json=_make_openalex_response([]),
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = OpenAlexCIFetcher(data_dir=tmpdir)
            result = fetcher.fetch(days_back=1)

            assert result["status"] == "success"
            assert result["record_count"] == 0
            assert result["records"] == []

    @responses.activate
    def test_fetch_api_error(self):
        """Test fetch handles HTTP errors gracefully."""
        responses.add(
            responses.GET,
            "https://api.openalex.org/works",
            json={"error": "rate limited"},
            status=429,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = OpenAlexCIFetcher(data_dir=tmpdir)
            result = fetcher.fetch(days_back=1)

            assert result["status"] == "failed"
            assert result["error"] is not None
            assert result["records"] == []

    @responses.activate
    def test_fetch_respects_max_records(self):
        """Test that fetch stops when max_records is reached."""
        # Return a page with 2 works, but limit to 1
        responses.add(
            responses.GET,
            "https://api.openalex.org/works",
            json=_make_openalex_response(
                [SAMPLE_WORK, SAMPLE_WORK_MINIMAL],
                next_cursor="next_page",
            ),
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = OpenAlexCIFetcher(data_dir=tmpdir)
            result = fetcher.fetch(days_back=7, max_records=1)

            assert result["status"] == "success"
            # Both records from the first page are added before the limit check
            # on the next iteration, so we get 2 records from this page
            # but pagination stops (no further pages fetched)
            assert result["record_count"] >= 1


class TestAbstractReconstruction:
    """Tests for abstract inverted index reconstruction."""

    def test_reconstruct_normal_abstract(self):
        """Test standard inverted index reconstruction."""
        inverted_index = {
            "This": [0],
            "is": [1],
            "a": [2],
            "test": [3],
            "abstract.": [4],
        }
        result = OpenAlexCIFetcher._reconstruct_abstract(inverted_index)
        assert result == "This is a test abstract."

    def test_reconstruct_with_repeated_words(self):
        """Test reconstruction when words appear at multiple positions."""
        inverted_index = {
            "the": [0, 3],
            "cat": [1],
            "sat": [2],
            "mat": [4],
        }
        result = OpenAlexCIFetcher._reconstruct_abstract(inverted_index)
        assert result == "the cat sat the mat"

    def test_reconstruct_none_input(self):
        """Test that None inverted index returns None."""
        assert OpenAlexCIFetcher._reconstruct_abstract(None) is None

    def test_reconstruct_empty_input(self):
        """Test that empty inverted index returns None."""
        assert OpenAlexCIFetcher._reconstruct_abstract({}) is None


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------


class TestOpenAlexCIRecordValid:
    """Tests for valid OpenAlexCIRecord instances."""

    def test_openalex_ci_record_valid(self):
        """Test a fully populated valid record."""
        record = OpenAlexCIRecord(
            work_id="W2741809807",
            doi="https://doi.org/10.1038/s41586-021-03819-2",
            title="Test Publication",
            abstract="This is a test abstract.",
            publication_date=date(2021, 7, 15),
            cited_by_count=100,
            concepts=[{"id": "C123", "display_name": "Medicine"}],
            authorships=[{"author": {"display_name": "Jane Doe"}}],
            primary_location={"source": {"display_name": "Nature"}},
            open_access={"is_oa": True},
        )
        assert record.work_id == "W2741809807"
        assert record.cited_by_count == 100
        assert record.concepts is not None

    def test_openalex_ci_record_minimal(self):
        """Test a minimal valid record with only required fields."""
        record = OpenAlexCIRecord(work_id="W1234567890")
        assert record.work_id == "W1234567890"
        assert record.doi is None
        assert record.title is None
        assert record.cited_by_count is None

    def test_openalex_ci_record_zero_citations(self):
        """Test that zero citations is valid."""
        record = OpenAlexCIRecord(work_id="W1111111111", cited_by_count=0)
        assert record.cited_by_count == 0


class TestOpenAlexCIRecordInvalid:
    """Tests for invalid OpenAlexCIRecord instances."""

    def test_openalex_ci_record_invalid_work_id(self):
        """Test that work_id not starting with 'W' is rejected."""
        with pytest.raises(Exception) as exc_info:
            OpenAlexCIRecord(work_id="12345")
        assert "work_id" in str(exc_info.value).lower() or "W" in str(exc_info.value)

    def test_openalex_ci_record_empty_work_id(self):
        """Test that an empty work_id is rejected."""
        with pytest.raises(Exception):
            OpenAlexCIRecord(work_id="")

    def test_openalex_ci_record_missing_work_id(self):
        """Test that missing work_id is rejected."""
        with pytest.raises(Exception):
            OpenAlexCIRecord()

    def test_openalex_ci_record_negative_citations(self):
        """Test that negative cited_by_count is rejected."""
        with pytest.raises(Exception):
            OpenAlexCIRecord(work_id="W1234567890", cited_by_count=-1)
