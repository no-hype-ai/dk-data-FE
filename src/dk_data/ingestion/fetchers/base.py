"""Base fetcher class with common functionality."""

import csv
import hashlib
import logging
import os
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_CMS_DATA_API = "https://data.cms.gov/data-api/v1/dataset"
_CMS_PAGE_SIZE = 2000

logger = logging.getLogger(__name__)


class BaseFetcher(ABC):
    """Base class for all data fetchers."""

    # Override in subclasses
    SOURCE_NAME: str = "base"
    BASE_URL: str = ""

    def __init__(
        self,
        data_dir: Optional[str] = None,
        max_retries: int = 3,
        retry_base_delay_seconds: float = 1.0,
    ):
        """
        Initialize fetcher.

        Args:
            data_dir: Directory to store downloaded files. Defaults to ./data/raw
            max_retries: Total retry attempts on transient errors (default 3).
                         Can be overridden per-source via SOURCES dict key ``max_retries``.
            retry_base_delay_seconds: urllib3 backoff_factor (delay = backoff_factor * 2^(n-1)).
                         Can be overridden per-source via SOURCES dict key ``retry_base_delay_seconds``.
        """
        self.data_dir = Path(data_dir or os.environ.get('DATA_DIR', './data/raw'))
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Per-source runtime params (e.g. max_records); populated by orchestrator or __init__ override.
        self.params: Dict[str, Any] = {}

        # Set up session with retry logic (per-source overridable via SOURCES dict)
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=retry_base_delay_seconds,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Common headers
        self.session.headers.update({
            'User-Agent': 'DataKinetic-Research/1.0 (academic-research-data-integration; +https://datakinetic.io)',
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

    def _fetch_cms_api(
        self,
        dataset_uuid: str,
        max_records: Optional[int] = None,
        filter_params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch records from the CMS data-api/v1 streaming endpoint.

        Args:
            dataset_uuid: CMS dataset UUID from data.cms.gov/data.json catalog.
            max_records: Cap on total rows. None = fetch all.
            filter_params: Optional extra query params for server-side filtering
                (e.g. {"filter[Rndrng_Prvdr_Type][value]": "Radiology"}).

        Returns:
            List of row dicts with CMS column names as returned by the API.
        """
        api_url = f"{_CMS_DATA_API}/{dataset_uuid}/data"
        records: List[Dict[str, Any]] = []
        offset = 0

        logger.info("[%s] Fetching from CMS data-api: %s", self.SOURCE_NAME, api_url)

        while True:
            remaining = None if max_records is None else max_records - len(records)
            if remaining is not None and remaining <= 0:
                break
            page_size = _CMS_PAGE_SIZE if remaining is None else min(_CMS_PAGE_SIZE, remaining)

            params: Dict[str, Any] = {"size": page_size, "offset": offset}
            if filter_params:
                params.update(filter_params)

            resp = self.session.get(api_url, params=params, timeout=60)
            resp.raise_for_status()
            page: List[Dict[str, Any]] = resp.json()
            if not page:
                break
            records.extend(page)
            logger.debug("[%s] Fetched %d records (offset=%d)", self.SOURCE_NAME, len(records), offset)
            if len(page) < page_size:
                break
            offset += page_size

        logger.info("[%s] %d total records fetched from CMS API", self.SOURCE_NAME, len(records))
        return records

    def _cms_records_to_csv(self, records: List[Dict[str, Any]]) -> str:
        """Write CMS API records to a temp CSV file.

        Returns:
            Path to the temp CSV file (caller is responsible for deletion).
        """
        if not records:
            raise ValueError("No records to write")
        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".csv",
            prefix=f"cms_{self.SOURCE_NAME}_",
            delete=False,
            newline="",
            encoding="utf-8",
        )
        writer = csv.DictWriter(tmp, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
        tmp.close()
        return tmp.name

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
