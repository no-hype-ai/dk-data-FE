"""Base fetcher class with common functionality."""

import os
import logging
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
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

    def __init__(self, data_dir: Optional[str] = None):
        """
        Initialize fetcher.

        Args:
            data_dir: Directory to store downloaded files. Defaults to ./data/raw
        """
        self.data_dir = Path(data_dir or os.environ.get('DATA_DIR', './data/raw'))
        self.data_dir.mkdir(parents=True, exist_ok=True)

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
