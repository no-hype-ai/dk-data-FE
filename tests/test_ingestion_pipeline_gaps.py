"""Tests for ingestion pipeline efficiency gaps: hash-skip, checkpoint resume, conditional HTTP.

Tests the three additive features:
1. Hash comparison to skip unchanged data loads
2. Pagination checkpoint resume from last failed offset
3. Conditional HTTP (If-None-Match / If-Modified-Since) support
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest  # noqa: F401 — pytest fixture/marker discovery
import responses

from dk_data.ingestion.fetchers.base import BaseFetcher


# ---------------------------------------------------------------------------
# Concrete fetcher for testing base class conditional methods
# ---------------------------------------------------------------------------

class StubFetcher(BaseFetcher):
    """Minimal fetcher for testing base class methods."""
    SOURCE_NAME = "stub"
    BASE_URL = "https://example.com"

    def fetch(self, **kwargs):
        return {"status": "success", "records": []}

    def get_latest_url(self):
        return f"{self.BASE_URL}/data"


# ===========================================================================
# Phase 2: BaseFetcher conditional HTTP methods
# ===========================================================================

class TestDownloadFileConditional:
    @responses.activate
    def test_304_not_modified(self):
        """download_file_conditional returns not_modified on 304."""
        responses.add(
            responses.GET,
            "https://example.com/data/file.zip",
            status=304,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = StubFetcher(data_dir=tmpdir)
            result = fetcher.download_file_conditional(
                "https://example.com/data/file.zip",
                "file.zip",
                etag='"abc123"',
                last_modified="Wed, 01 Jan 2025 00:00:00 GMT",
            )
            assert result["status"] == "not_modified"
            assert result["etag"] == '"abc123"'
            assert result["last_modified"] == "Wed, 01 Jan 2025 00:00:00 GMT"

    @responses.activate
    def test_200_downloads_file(self):
        """download_file_conditional downloads and captures headers on 200."""
        responses.add(
            responses.GET,
            "https://example.com/data/file.zip",
            body=b"file-content-here",
            status=200,
            headers={
                "ETag": '"new-etag"',
                "Last-Modified": "Thu, 02 Jan 2025 00:00:00 GMT",
            },
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = StubFetcher(data_dir=tmpdir)
            result = fetcher.download_file_conditional(
                "https://example.com/data/file.zip",
                "file.zip",
                etag='"old-etag"',
            )
            assert result["status"] == "downloaded"
            assert result["filepath"] == Path(tmpdir) / "file.zip"
            assert result["filepath"].read_bytes() == b"file-content-here"
            assert result["etag"] == '"new-etag"'
            assert result["last_modified"] == "Thu, 02 Jan 2025 00:00:00 GMT"

    @responses.activate
    def test_sends_if_none_match_header(self):
        """download_file_conditional sends If-None-Match when etag provided."""
        responses.add(
            responses.GET,
            "https://example.com/data/file.zip",
            body=b"data",
            status=200,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = StubFetcher(data_dir=tmpdir)
            fetcher.download_file_conditional(
                "https://example.com/data/file.zip",
                "file.zip",
                etag='"my-etag"',
            )
            assert responses.calls[0].request.headers["If-None-Match"] == '"my-etag"'

    @responses.activate
    def test_sends_if_modified_since_header(self):
        """download_file_conditional sends If-Modified-Since when last_modified provided."""
        responses.add(
            responses.GET,
            "https://example.com/data/file.zip",
            body=b"data",
            status=200,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = StubFetcher(data_dir=tmpdir)
            fetcher.download_file_conditional(
                "https://example.com/data/file.zip",
                "file.zip",
                last_modified="Wed, 01 Jan 2025 00:00:00 GMT",
            )
            assert responses.calls[0].request.headers["If-Modified-Since"] == "Wed, 01 Jan 2025 00:00:00 GMT"


class TestFetchJsonConditional:
    @responses.activate
    def test_304_not_modified(self):
        """fetch_json_conditional returns not_modified on 304."""
        responses.add(
            responses.GET,
            "https://example.com/api/data",
            status=304,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = StubFetcher(data_dir=tmpdir)
            result = fetcher.fetch_json_conditional(
                "https://example.com/api/data",
                etag='"etag-val"',
            )
            assert result["status"] == "not_modified"
            assert result["data"] is None
            assert result["etag"] == '"etag-val"'

    @responses.activate
    def test_200_returns_data(self):
        """fetch_json_conditional returns data and headers on 200."""
        responses.add(
            responses.GET,
            "https://example.com/api/data",
            json={"items": [1, 2, 3]},
            status=200,
            headers={"ETag": '"resp-etag"'},
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = StubFetcher(data_dir=tmpdir)
            result = fetcher.fetch_json_conditional(
                "https://example.com/api/data",
            )
            assert result["status"] == "ok"
            assert result["data"] == {"items": [1, 2, 3]}
            assert result["etag"] == '"resp-etag"'

    @responses.activate
    def test_no_headers_when_none_provided(self):
        """fetch_json_conditional does not send conditional headers when not provided."""
        responses.add(
            responses.GET,
            "https://example.com/api/data",
            json={},
            status=200,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = StubFetcher(data_dir=tmpdir)
            fetcher.fetch_json_conditional("https://example.com/api/data")
            req_headers = responses.calls[0].request.headers
            assert "If-None-Match" not in req_headers
            assert "If-Modified-Since" not in req_headers


# ===========================================================================
# Phase 3: main.py hash-skip + checkpoint + conditional HTTP orchestration
# ===========================================================================

class TestGetLastContentHash:
    @patch("dk_data.ingestion.main.get_cursor")
    def test_returns_hash_when_present(self, mock_get_cursor):
        from dk_data.ingestion.main import get_last_content_hash

        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = ("abc123def456",)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        assert get_last_content_hash("cms_rbcs") == "abc123def456"

    @patch("dk_data.ingestion.main.get_cursor")
    def test_returns_none_when_no_row(self, mock_get_cursor):
        from dk_data.ingestion.main import get_last_content_hash

        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        assert get_last_content_hash("cms_rbcs") is None

    @patch("dk_data.ingestion.main.get_cursor")
    def test_returns_none_on_exception(self, mock_get_cursor):
        from dk_data.ingestion.main import get_last_content_hash

        mock_get_cursor.side_effect = Exception("connection error")
        assert get_last_content_hash("cms_rbcs") is None


class TestGetConditionalHeaders:
    @patch("dk_data.ingestion.main.get_cursor")
    def test_returns_headers(self, mock_get_cursor):
        from dk_data.ingestion.main import get_conditional_headers

        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = ('"etag-val"', "Wed, 01 Jan 2025 00:00:00 GMT")
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        result = get_conditional_headers("cms_nppes")
        assert result["etag"] == '"etag-val"'
        assert result["last_modified"] == "Wed, 01 Jan 2025 00:00:00 GMT"

    @patch("dk_data.ingestion.main.get_cursor")
    def test_returns_defaults_on_exception(self, mock_get_cursor):
        from dk_data.ingestion.main import get_conditional_headers

        mock_get_cursor.side_effect = Exception("db error")
        result = get_conditional_headers("cms_nppes")
        assert result == {"etag": None, "last_modified": None}


class TestGetCheckpointOffset:
    @patch("dk_data.ingestion.main.get_cursor")
    def test_returns_offset_from_failed_run(self, mock_get_cursor):
        from dk_data.ingestion.main import get_checkpoint_offset

        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (1500,)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        assert get_checkpoint_offset("cms_open_payments") == 1500

    @patch("dk_data.ingestion.main.get_cursor")
    def test_returns_zero_when_no_checkpoint(self, mock_get_cursor):
        from dk_data.ingestion.main import get_checkpoint_offset

        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        assert get_checkpoint_offset("cms_open_payments") == 0

    @patch("dk_data.ingestion.main.get_cursor")
    def test_returns_zero_on_exception(self, mock_get_cursor):
        from dk_data.ingestion.main import get_checkpoint_offset

        mock_get_cursor.side_effect = Exception("db error")
        assert get_checkpoint_offset("cms_open_payments") == 0


class TestRunIngestionHashSkip:
    """Test that run_ingestion skips load when hash is unchanged."""

    @patch("dk_data.ingestion.main.log_to_meta")
    @patch("dk_data.ingestion.main.get_last_content_hash")
    @patch("dk_data.ingestion.main.get_checkpoint_offset", return_value=0)
    @patch("dk_data.ingestion.main.get_conditional_headers", return_value={"etag": None, "last_modified": None})
    def test_hash_skip_when_unchanged(
        self, mock_cond, mock_ckpt, mock_hash, mock_log
    ):
        from dk_data.ingestion.main import run_ingestion

        # Previous hash matches current fetch hash
        mock_hash.return_value = "deadbeef1234"

        mock_fetcher = MagicMock()
        mock_fetcher.return_value.fetch.return_value = {
            "status": "success",
            "records": [{"id": 1}],
            "hash": "deadbeef1234",
        }

        with patch.dict(
            "dk_data.ingestion.main.SOURCES",
            {
                "test_src": {
                    "name": "Test",
                    "description": "test",
                    "fetcher": mock_fetcher,
                    "loader": MagicMock(),
                    "requires_file": False,
                    "default_days_back": None,
                }
            },
        ):
            result = run_ingestion("test_src")

        assert result["status"] == "skipped"
        assert result["skipped_by_hash"] is True
        # Loader should NOT have been called
        mock_fetcher.return_value.fetch.assert_called_once()

    @patch("dk_data.ingestion.main.log_to_meta")
    @patch("dk_data.ingestion.main.get_last_content_hash")
    @patch("dk_data.ingestion.main.get_checkpoint_offset", return_value=0)
    @patch("dk_data.ingestion.main.get_conditional_headers", return_value={"etag": None, "last_modified": None})
    def test_hash_skip_disabled_for_ephemeral(
        self, mock_cond, mock_ckpt, mock_hash, mock_log
    ):
        from dk_data.ingestion.main import run_ingestion

        mock_hash.return_value = "deadbeef1234"

        mock_loader = MagicMock(return_value={
            "status": "success",
            "records_inserted": 1,
            "records_updated": 0,
        })
        mock_fetcher = MagicMock()
        mock_fetcher.return_value.fetch.return_value = {
            "status": "success",
            "records": [{"id": 1}],
            "hash": "deadbeef1234",
        }

        with patch.dict(
            "dk_data.ingestion.main.SOURCES",
            {
                "test_ephemeral": {
                    "name": "Test Ephemeral",
                    "description": "test",
                    "fetcher": mock_fetcher,
                    "loader": mock_loader,
                    "requires_file": False,
                    "default_days_back": None,
                    "hash_skip_enabled": False,
                }
            },
        ):
            result = run_ingestion("test_ephemeral")

        # Should NOT skip — loader should be called
        mock_loader.assert_called_once()
        assert result["status"] == "success"


class TestRunIngestionCheckpointResume:
    """Test that run_ingestion passes resume_offset to fetcher."""

    @patch("dk_data.ingestion.main.log_to_meta")
    @patch("dk_data.ingestion.main.get_last_content_hash", return_value=None)
    @patch("dk_data.ingestion.main.get_checkpoint_offset", return_value=5000)
    @patch("dk_data.ingestion.main.get_conditional_headers", return_value={"etag": None, "last_modified": None})
    def test_resume_offset_passed_to_fetcher(
        self, mock_cond, mock_ckpt, mock_hash, mock_log
    ):
        from dk_data.ingestion.main import run_ingestion

        mock_loader = MagicMock(return_value={
            "status": "success",
            "records_inserted": 10,
            "records_updated": 0,
        })
        mock_fetcher = MagicMock()
        mock_fetcher.return_value.fetch.return_value = {
            "status": "success",
            "records": [{"id": i} for i in range(10)],
            "hash": "newhash",
        }

        with patch.dict(
            "dk_data.ingestion.main.SOURCES",
            {
                "test_checkpoint": {
                    "name": "Test Checkpoint",
                    "description": "test",
                    "fetcher": mock_fetcher,
                    "loader": mock_loader,
                    "requires_file": False,
                    "default_days_back": None,
                }
            },
        ):
            run_ingestion("test_checkpoint")

        # Verify resume_offset was passed to fetcher
        call_kwargs = mock_fetcher.return_value.fetch.call_args
        assert call_kwargs[1].get("resume_offset") == 5000


class TestRunIngestionConditionalHTTP:
    """Test that run_ingestion passes conditional HTTP headers to fetcher."""

    @patch("dk_data.ingestion.main.log_to_meta")
    @patch("dk_data.ingestion.main.get_last_content_hash", return_value=None)
    @patch("dk_data.ingestion.main.get_checkpoint_offset", return_value=0)
    @patch(
        "dk_data.ingestion.main.get_conditional_headers",
        return_value={"etag": '"cached-etag"', "last_modified": "Mon, 01 Jan 2025 00:00:00 GMT"},
    )
    def test_etag_and_last_modified_passed_to_fetcher(
        self, mock_cond, mock_ckpt, mock_hash, mock_log
    ):
        from dk_data.ingestion.main import run_ingestion

        mock_loader = MagicMock(return_value={
            "status": "success",
            "records_inserted": 5,
            "records_updated": 0,
        })
        mock_fetcher = MagicMock()
        mock_fetcher.return_value.fetch.return_value = {
            "status": "success",
            "records": [{"id": 1}],
            "hash": "somehash",
        }

        with patch.dict(
            "dk_data.ingestion.main.SOURCES",
            {
                "test_cond": {
                    "name": "Test Conditional",
                    "description": "test",
                    "fetcher": mock_fetcher,
                    "loader": mock_loader,
                    "requires_file": False,
                    "default_days_back": None,
                }
            },
        ):
            run_ingestion("test_cond")

        call_kwargs = mock_fetcher.return_value.fetch.call_args[1]
        assert call_kwargs["etag"] == '"cached-etag"'
        assert call_kwargs["last_modified"] == "Mon, 01 Jan 2025 00:00:00 GMT"

    @patch("dk_data.ingestion.main.log_to_meta")
    @patch("dk_data.ingestion.main.get_last_content_hash", return_value=None)
    @patch("dk_data.ingestion.main.get_checkpoint_offset", return_value=0)
    @patch(
        "dk_data.ingestion.main.get_conditional_headers",
        return_value={"etag": '"cached-etag"', "last_modified": None},
    )
    def test_not_modified_skips_load(
        self, mock_cond, mock_ckpt, mock_hash, mock_log
    ):
        from dk_data.ingestion.main import run_ingestion

        mock_loader = MagicMock()
        mock_fetcher = MagicMock()
        mock_fetcher.return_value.fetch.return_value = {
            "status": "not_modified",
            "records": [],
            "hash": None,
        }

        with patch.dict(
            "dk_data.ingestion.main.SOURCES",
            {
                "test_304": {
                    "name": "Test 304",
                    "description": "test",
                    "fetcher": mock_fetcher,
                    "loader": mock_loader,
                    "requires_file": False,
                    "default_days_back": None,
                }
            },
        ):
            result = run_ingestion("test_304")

        assert result["status"] == "skipped"
        assert result["skipped_by_hash"] is True
        mock_loader.assert_not_called()


# ===========================================================================
# Phase 4: Fetcher checkpoint support
# ===========================================================================

class TestFetcherResumeOffset:
    """Verify paginated fetchers honour resume_offset kwarg."""

    @responses.activate
    def test_cms_rbcs_resumes_from_offset(self):
        """CMSRBCSFetcher starts pagination at resume_offset."""
        from dk_data.ingestion.fetchers.cms_rbcs import CMSRBCSFetcher

        # Return one page then empty to end pagination
        responses.add(
            responses.GET,
            url="https://data.cms.gov/data-api/v1/dataset/e3db6e56-149f-49ce-b374-40aecda2357b/data",
            json=[{"HCPCS_CD": "99213", "RBCS_ID": "1", "RBCS_CAT": "E&M",
                   "RBCS_SUBCAT": "Office", "RBCS_FAMILY": "Visit"}],
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = CMSRBCSFetcher(data_dir=tmpdir)
            result = fetcher.fetch(resume_offset=2000)

        # Verify the request used the resume offset
        assert "offset=2000" in responses.calls[0].request.url
        assert result["status"] == "success"

    @responses.activate
    def test_cms_rbcs_tracks_last_offset_on_failure(self):
        """CMSRBCSFetcher captures _last_offset in error result."""
        from dk_data.ingestion.fetchers.cms_rbcs import CMSRBCSFetcher

        # First page succeeds, second fails
        responses.add(
            responses.GET,
            url="https://data.cms.gov/data-api/v1/dataset/e3db6e56-149f-49ce-b374-40aecda2357b/data",
            json=[{"HCPCS_CD": f"CODE{i}", "RBCS_ID": str(i), "RBCS_CAT": "cat",
                   "RBCS_SUBCAT": "sub", "RBCS_FAMILY": "fam"} for i in range(1000)],
            status=200,
        )
        responses.add(
            responses.GET,
            url="https://data.cms.gov/data-api/v1/dataset/e3db6e56-149f-49ce-b374-40aecda2357b/data",
            json={"error": "server error"},
            status=500,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = CMSRBCSFetcher(data_dir=tmpdir)
            result = fetcher.fetch()

        assert result["status"] == "failed"
        assert result.get("last_offset", 0) >= 0


class TestLogToMetaNewColumns:
    """Verify log_to_meta passes new columns to SQL."""

    @patch("dk_data.ingestion.main.get_cursor")
    def test_log_includes_content_hash_and_offset(self, mock_get_cursor):
        from dk_data.ingestion.main import log_to_meta

        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (42,)  # source_id
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        log_to_meta("cms_rbcs", {
            "status": "success",
            "records_inserted": 100,
            "records_updated": 0,
            "content_hash": "abc123",
            "last_offset": 5000,
            "skipped_by_hash": False,
            "etag": '"my-etag"',
            "last_modified": "Thu, 01 Jan 2025 00:00:00 GMT",
        })

        # Verify INSERT was called with new columns
        insert_call = mock_cur.execute.call_args_list[1]  # second execute = INSERT
        insert_sql = insert_call[0][0]
        assert "content_hash" in insert_sql
        assert "pagination_offset" in insert_sql
        assert "skipped_by_hash" in insert_sql

        insert_params = insert_call[0][1]
        assert "abc123" in insert_params
        assert 5000 in insert_params
        assert False in insert_params

        # Verify UPDATE was called with new columns
        update_call = mock_cur.execute.call_args_list[2]  # third execute = UPDATE
        update_sql = update_call[0][0]
        assert "last_content_hash" in update_sql
        assert "last_etag" in update_sql
        assert "last_modified_header" in update_sql
