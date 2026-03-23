"""Base fetcher class with common functionality."""

import json
import os
import logging
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class BaseFetcher(ABC):
    """Base class for all data fetchers."""

    # Override in subclasses
    SOURCE_NAME: str = "base"
    BASE_URL: str = ""

    def __init__(self, data_dir: Optional[str] = None, params: Optional[Dict[str, Any]] = None):
        """
        Initialize fetcher.

        Args:
            data_dir: Directory to store downloaded files. Defaults to ./data/raw
            params: Generic parameters dict for source-specific configuration
                    (e.g., year, state, file_type). Passed from CronJob args.
        """
        self.data_dir = Path(data_dir or os.environ.get('DATA_DIR', './data/raw'))
        self.params = params or {}
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Manifest directory: data/raw/.manifests/<source_name>.json
        self._manifest_dir = self.data_dir / '.manifests'
        self._manifest_dir.mkdir(parents=True, exist_ok=True)

        # Set up session with retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Common headers
        self.session.headers.update({
            'User-Agent': 'TAVR-Data-Platform/1.0 (Edwards Medical; Data Integration)',
            'Accept': 'application/json, text/csv, */*',
        })

    @abstractmethod
    def fetch(self, **kwargs) -> Dict[str, Any]:
        """
        Fetch data from the source.

        Returns:
            Dictionary with fetch results including:
            - status: 'success' or 'failed'
            - filepath: Path to downloaded file (if applicable)
            - records: Number of records fetched
            - error: Error message (if failed)
        """
        pass

    @abstractmethod
    def get_latest_url(self) -> str:
        """Get URL for the latest data file."""
        pass

    def download_file(self, url: str, filename: str) -> Path:
        """
        Download a file from URL.

        Args:
            url: URL to download from
            filename: Local filename to save as

        Returns:
            Path to downloaded file
        """
        filepath = self.data_dir / filename
        logger.info(f"Downloading {url} to {filepath}")

        response = self.session.get(url, stream=True, timeout=300)
        response.raise_for_status()

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"Downloaded {filepath.stat().st_size / 1024 / 1024:.2f} MB")
        return filepath

    def calculate_hash(self, filepath: Path) -> str:
        """Calculate MD5 hash of a file."""
        hash_md5 = hashlib.md5()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def fetch_json(self, url: str, params: Optional[Dict] = None) -> Dict:
        """
        Fetch JSON data from an API endpoint.

        Args:
            url: API URL
            params: Query parameters

        Returns:
            JSON response as dictionary
        """
        logger.debug(f"Fetching JSON from {url}")
        response = self.session.get(url, params=params, timeout=60)
        response.raise_for_status()
        return response.json()

    def download_file_conditional(
        self,
        url: str,
        filename: str,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        use_manifest: bool = True,
    ) -> Dict[str, Any]:
        """Download a file, skipping if upstream hasn't changed (304 Not Modified).

        If use_manifest=True (default) the ETag and Last-Modified values are
        automatically loaded from the manifest before the request and saved
        back after a successful download.

        Args:
            url: URL to download from.
            filename: Local filename to save as.
            etag: ETag override (overrides manifest value when provided).
            last_modified: Last-Modified override (overrides manifest value).
            use_manifest: If True, auto-load/save ETag + Last-Modified to manifest.

        Returns:
            Dict with 'status' ('downloaded' or 'not_modified'), 'filepath',
            'etag', and 'last_modified'.
        """
        if use_manifest:
            manifest = self.load_manifest()
            etag = etag or manifest.get('etag')
            last_modified = last_modified or manifest.get('last_modified')

        headers: Dict[str, str] = {}
        if etag:
            headers['If-None-Match'] = etag
        if last_modified:
            headers['If-Modified-Since'] = last_modified

        filepath = self.data_dir / filename
        logger.info(f"Conditional download {url} to {filepath}")

        response = self.session.get(url, stream=True, timeout=300, headers=headers)

        if response.status_code == 304:
            logger.info(f"[{self.SOURCE_NAME}] 304 Not Modified for {url}")
            return {
                "status": "not_modified",
                "filepath": filepath if filepath.exists() else None,
                "etag": etag,
                "last_modified": last_modified,
            }

        response.raise_for_status()

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        new_etag = response.headers.get('ETag', etag)
        new_last_modified = response.headers.get('Last-Modified', last_modified)

        logger.info(f"Downloaded {filepath.stat().st_size / 1024 / 1024:.2f} MB")

        if use_manifest:
            self.save_manifest(
                last_run_at=datetime.now(timezone.utc).isoformat(),
                last_run_status="completed",
                etag=new_etag,
                last_modified=new_last_modified,
            )

        return {
            "status": "downloaded",
            "filepath": filepath,
            "etag": new_etag,
            "last_modified": new_last_modified,
        }

    def fetch_json_conditional(
        self,
        url: str,
        params: Optional[Dict] = None,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        use_manifest: bool = True,
    ) -> Dict[str, Any]:
        """Fetch JSON, returning early on 304 Not Modified.

        If use_manifest=True (default) the ETag and Last-Modified values are
        automatically loaded from the manifest before the request and saved
        back after a successful fetch.

        Args:
            url: API URL.
            params: Query parameters.
            etag: ETag override (overrides manifest value when provided).
            last_modified: Last-Modified override (overrides manifest value).
            use_manifest: If True, auto-load/save ETag + Last-Modified to manifest.

        Returns:
            Dict with 'status' ('ok' or 'not_modified'), 'data', 'etag',
            and 'last_modified'.
        """
        if use_manifest:
            manifest = self.load_manifest()
            etag = etag or manifest.get('etag')
            last_modified = last_modified or manifest.get('last_modified')

        headers: Dict[str, str] = {}
        if etag:
            headers['If-None-Match'] = etag
        if last_modified:
            headers['If-Modified-Since'] = last_modified

        logger.debug(f"Conditional JSON fetch from {url}")
        response = self.session.get(url, params=params, timeout=60, headers=headers)

        if response.status_code == 304:
            logger.info(f"[{self.SOURCE_NAME}] 304 Not Modified for {url}")
            return {
                "status": "not_modified",
                "data": None,
                "etag": etag,
                "last_modified": last_modified,
            }

        response.raise_for_status()
        new_etag = response.headers.get('ETag', etag)
        new_last_modified = response.headers.get('Last-Modified', last_modified)

        if use_manifest:
            self.save_manifest(etag=new_etag, last_modified=new_last_modified)

        return {
            "status": "ok",
            "data": response.json(),
            "etag": new_etag,
            "last_modified": new_last_modified,
        }

    def close(self) -> None:
        """Close the underlying HTTP session to release connections."""
        if self.session:
            self.session.close()

    def __del__(self) -> None:
        """Best-effort cleanup on garbage collection."""
        try:
            self.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Manifest: persist fetch state across runs (ETag, cursor, offsets)
    # ------------------------------------------------------------------

    @property
    def _manifest_path(self) -> Path:
        """Path to this source's manifest JSON file."""
        return self._manifest_dir / f"{self.SOURCE_NAME}.json"

    def load_manifest(self) -> Dict[str, Any]:
        """Load the persisted fetch state for this source.

        Returns an empty dict if no manifest exists yet.

        Manifest fields (all optional):
            last_run_at (str):        ISO timestamp of last completed run.
            last_run_status (str):    'completed' | 'interrupted' | 'failed'.
            total_records_fetched (int): Records fetched in last completed run.
            last_content_hash (str):  MD5 of last result set (change detection).
            etag (str):               HTTP ETag from last response (conditional requests).
            last_modified (str):      HTTP Last-Modified from last response.
            last_cursor (str|None):   Cursor marker to resume pagination.
            last_offset (int):        Numeric offset to resume pagination.
        """
        if not self._manifest_path.exists():
            return {}
        try:
            with open(self._manifest_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[{self.SOURCE_NAME}] Could not read manifest: {e}")
            return {}

    def save_manifest(self, **kwargs: Any) -> None:
        """Persist fetch state to the manifest file.

        Merges kwargs into any existing manifest (preserves fields not overwritten).
        Always updates `saved_at` to the current UTC timestamp.
        """
        manifest = self.load_manifest()
        manifest.update(kwargs)
        manifest['saved_at'] = datetime.now(timezone.utc).isoformat()
        try:
            with open(self._manifest_path, 'w') as f:
                json.dump(manifest, f, indent=2)
        except OSError as e:
            logger.warning(f"[{self.SOURCE_NAME}] Could not write manifest: {e}")

    def data_unchanged(self, new_hash: Optional[str]) -> bool:
        """Return True if new_hash matches the last saved content hash.

        Lets callers skip expensive processing when upstream hasn't changed.
        """
        if not new_hash:
            return False
        return self.load_manifest().get('last_content_hash') == new_hash

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------

    def log_fetch_result(self, result: Dict[str, Any]) -> None:
        """Log fetch result for monitoring."""
        timestamp = datetime.now().isoformat()
        status = result.get('status', 'unknown')
        records = result.get('records', 0)

        if status == 'success':
            logger.info(f"[{self.SOURCE_NAME}] Fetch successful: {records} records at {timestamp}")
        else:
            error = result.get('error', 'Unknown error')
            logger.error(f"[{self.SOURCE_NAME}] Fetch failed: {error} at {timestamp}")
