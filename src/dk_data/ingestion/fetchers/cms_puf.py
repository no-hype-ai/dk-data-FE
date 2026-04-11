"""CMS PUF (Public Use File) Base Fetcher Utilities.

Feature: 001-silver-medallion-rebuild
Task: T092 — HTTP Range resume support for large CMS PUF downloads

Provides _resume_download() for resuming partial downloads of large CMS PUF
files using the HTTP Range header. Used by individual PUF fetchers.
"""

import logging
import os
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Chunk size for streaming downloads (8 MB)
_CHUNK_SIZE = 8 * 1024 * 1024


def _resume_download(url: str, dest_path: str, session: Optional[requests.Session] = None) -> str:
    """Download a file from URL with HTTP Range resume support.

    If dest_path already exists (partial download), resumes from where it left
    off by sending an HTTP Range header. Falls back to a full download if the
    server does not support range requests (no 206 Partial Content).

    Args:
        url: URL to download from.
        dest_path: Local filesystem path to write the file to.
        session: Optional requests.Session to use (creates a new one if not provided).

    Returns:
        dest_path on success.

    Raises:
        requests.HTTPError: If the server returns an error response.
        IOError: If writing to dest_path fails.
    """
    dest = Path(dest_path)
    existing_size = dest.stat().st_size if dest.exists() else 0

    sess = session or requests.Session()
    headers = {}

    if existing_size > 0:
        headers["Range"] = f"bytes={existing_size}-"
        logger.info(
            "Resuming download from byte %d: %s -> %s",
            existing_size, url, dest_path,
        )
    else:
        logger.info("Starting download: %s -> %s", url, dest_path)

    response = sess.get(url, headers=headers, stream=True, timeout=300)

    # 416 = Range Not Satisfiable (already fully downloaded)
    if response.status_code == 416:
        logger.info("File already fully downloaded (416): %s", dest_path)
        return dest_path

    response.raise_for_status()

    # 206 = partial content (server supports resume)
    # 200 = server doesn't support range; restart from scratch
    if response.status_code == 200 and existing_size > 0:
        logger.warning(
            "Server does not support Range requests (200 instead of 206). "
            "Restarting download from scratch: %s", url
        )
        existing_size = 0
        dest.unlink(missing_ok=True)

    mode = "ab" if existing_size > 0 else "wb"
    bytes_written = 0

    with open(dest_path, mode) as f:
        for chunk in response.iter_content(chunk_size=_CHUNK_SIZE):
            if chunk:
                f.write(chunk)
                bytes_written += len(chunk)

    total_size = existing_size + bytes_written
    logger.info(
        "Download complete: %s (%.1f MB total, %.1f MB written this session)",
        dest_path,
        total_size / 1024 / 1024,
        bytes_written / 1024 / 1024,
    )
    return dest_path
