"""Regression tests for cms_downloader zip extraction + Content-Length guard.

Covers plan §B.4 (PR-03):

* Multi-file zips extract EVERY member (NPPES regression — the old code
  silently dropped 3-of-4 files).
* Content-Length header mismatches trigger the retry-once / fail-loudly guard
  and increment the dk_artifact_size_mismatch_total counter.
* The legacy single-path ``download_cms_file`` call site keeps working.
* The new ``download_cms_files`` call site returns every extracted artefact.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal ``requests.Response`` stand-in with streaming support."""

    def __init__(self, body: bytes, content_type: str = "application/zip",
                 content_length: Optional[int] = None, status: int = 200):
        self._body = body
        self.status_code = status
        self.headers: Dict[str, str] = {"content-type": content_type}
        if content_length is not None:
            # Allow simulating truncated responses where header != body length.
            self.headers["Content-Length"] = str(content_length)
        else:
            self.headers["Content-Length"] = str(len(body))

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int = 65536):
        buf = self._body
        for i in range(0, len(buf), chunk_size):
            yield buf[i:i + chunk_size]


def _build_zip(files: Dict[str, bytes]) -> bytes:
    """Build an in-memory zip archive containing the given files."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_download_dir(tmp_path, monkeypatch):
    """Point cms_downloader.DOWNLOAD_DIR at a tmp directory for the test.

    Do NOT hardcode DOWNLOAD_DIR (plan constraint) — we override by mutating
    the module attribute under monkeypatch so the production default (env
    var) still wins in real deployments.
    """
    from dk_data.ingestion.downloaders import cms_downloader

    monkeypatch.setattr(cms_downloader, "DOWNLOAD_DIR", tmp_path)
    # also reset the cached catalog path to avoid leaking real env state
    monkeypatch.setattr(
        cms_downloader,
        "_CATALOG_CACHE_PATH",
        tmp_path / "_cms_catalog.json",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_zip_with_three_csvs_extracts_all_three(isolated_download_dir):
    """The NPPES regression — plan §A.1.

    Build a zip with three CSVs of different sizes, drive it through
    download_cms_files, and confirm every file ends up on disk and is
    returned to the caller.
    """
    from dk_data.ingestion.downloaders import cms_downloader

    files = {
        "small.csv": b"col1,col2\nv1,v2\n",
        "medium.csv": b"col1,col2\n" + (b"row,val\n" * 500),
        "large.csv": b"col1,col2\n" + (b"row,val\n" * 5000),
    }
    zip_bytes = _build_zip(files)
    fake_url = "https://download.cms.gov/nppes/fake_bundle.zip"

    with patch.object(cms_downloader, "_get_download_url", return_value=fake_url), \
         patch.object(cms_downloader.requests, "get",
                      return_value=_FakeResponse(zip_bytes)):
        paths, was_new = cms_downloader.download_cms_files(
            "cms_testfixture_multizip", year=2099
        )

    assert was_new is True, "expected fresh download, not cache hit"
    assert paths, "expected at least one extracted file"

    # All three CSVs must be on disk under the extraction directory.
    extract_dir = isolated_download_dir / "cms_testfixture_multizip_2099_extracted"
    on_disk = sorted(p.name for p in extract_dir.iterdir() if p.is_file())
    assert on_disk == ["large.csv", "medium.csv", "small.csv"], (
        f"Expected all 3 CSVs extracted; got {on_disk}"
    )

    # Every CSV content matches exactly.
    for name, expected_bytes in files.items():
        assert (extract_dir / name).read_bytes() == expected_bytes

    # download_cms_file (legacy single-path API) returns the largest file.
    with patch.object(cms_downloader, "_get_download_url", return_value=fake_url), \
         patch.object(cms_downloader.requests, "get",
                      return_value=_FakeResponse(zip_bytes)):
        single_path, _ = cms_downloader.download_cms_file(
            "cms_testfixture_multizip", year=2099, force=True
        )
    assert single_path is not None
    assert Path(single_path).read_bytes() == files["large.csv"], (
        "Single-path API must return the primary/largest file for backwards compat"
    )


def test_content_length_mismatch_retries_once_then_fails(isolated_download_dir):
    """Plan §B.4 integrity guard.

    Simulate an upstream that advertises Content-Length=1000 but only streams
    500 bytes.  Expect: first attempt fails → retry → second attempt also
    mismatches → function returns ([], False) and the mismatch counter is
    incremented twice.
    """
    from dk_data.ingestion.downloaders import cms_downloader

    body = b"x" * 500
    responses: List[_FakeResponse] = [
        _FakeResponse(body, content_type="text/csv", content_length=1000),
        _FakeResponse(body, content_type="text/csv", content_length=1000),
    ]

    counter_values: List[int] = []

    def fake_get(*_args, **_kwargs):
        return responses.pop(0)

    labelled = cms_downloader.DK_ARTIFACT_SIZE_MISMATCH_TOTAL.labels(
        source="cms_testfixture_shortbody"
    )

    def _snapshot():
        # prometheus_client Counter._value is atomic; fall back to 0 if no
        # underlying value exposed (noop counter in pure unit test env).
        val = getattr(labelled, "_value", None)
        return val.get() if val is not None else 0

    before = _snapshot()

    with patch.object(
        cms_downloader, "_get_download_url",
        return_value="https://cms.example/puf.csv",
    ), patch.object(cms_downloader.requests, "get", side_effect=fake_get):
        paths, was_new = cms_downloader.download_cms_files(
            "cms_testfixture_shortbody", year=2099
        )

    assert paths == []
    assert was_new is False

    after = _snapshot()
    # Only assert delta when we have a real Counter attached; noop mode skips.
    if hasattr(labelled, "_value") and labelled._value is not None:
        assert after - before == 2, (
            f"Expected two size-mismatch events (one per attempt); got {after - before}"
        )

    # Tmp file must be cleaned up on failure.
    tmp_leftovers = list(isolated_download_dir.glob("*.tmp"))
    assert tmp_leftovers == [], f"Leftover .tmp files: {tmp_leftovers}"


def test_content_length_match_writes_sidecar(isolated_download_dir):
    """Sidecar must record Content-Length + SHA256 alongside legacy md5."""
    from dk_data.ingestion.downloaders import cms_downloader

    body = b"col1,col2\nfoo,bar\n"
    with patch.object(
        cms_downloader, "_get_download_url",
        return_value="https://cms.example/plain.csv",
    ), patch.object(
        cms_downloader.requests, "get",
        return_value=_FakeResponse(body, content_type="text/csv"),
    ):
        paths, was_new = cms_downloader.download_cms_files(
            "cms_testfixture_plain", year=2099
        )

    assert was_new is True
    assert len(paths) == 1

    sidecar = isolated_download_dir / "cms_testfixture_plain_2099.md5"
    assert sidecar.exists(), "sidecar file <cache>.md5 must be written"
    content = sidecar.read_text().splitlines()
    assert len(content) >= 3, f"sidecar must contain md5, sha256, content_length: {content}"
    assert len(content[0]) == 32, "first line must remain the md5 digest for legacy callers"
    assert any(line.startswith("sha256=") for line in content)
    assert any(
        line.startswith("content_length=") and line.endswith(str(len(body)))
        for line in content
    )


def test_zip_slip_is_rejected(isolated_download_dir):
    """A malicious zip with ``../`` path traversal must not escape the target."""
    from dk_data.ingestion.downloaders import cms_downloader

    # Craft a zip with an entry whose name escapes the extraction dir.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../etc/evil.csv", b"pwn")
        zf.writestr("good.csv", b"col1\nok\n")
    zip_bytes = buf.getvalue()

    with patch.object(
        cms_downloader, "_get_download_url",
        return_value="https://cms.example/evil.zip",
    ), patch.object(
        cms_downloader.requests, "get",
        return_value=_FakeResponse(zip_bytes, content_type="application/zip"),
    ):
        paths, was_new = cms_downloader.download_cms_files(
            "cms_testfixture_zipslip", year=2099
        )

    # Extraction aborts before any file is committed to cache_path,
    # so the helper returns ([], False).
    assert paths == []
    assert was_new is False
