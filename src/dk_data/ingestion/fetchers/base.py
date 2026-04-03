"""Base fetcher class with common functionality."""

import csv
import hashlib
import logging
import os
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable, Tuple

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
        response = self.session.get(url, params=params, timeout=120)
        response.raise_for_status()
        return response.json()

    def _fetch_cms_api_to_csv(
        self,
        dataset_uuid: str,
        max_records: Optional[int] = None,
        filter_params: Optional[Dict[str, Any]] = None,
        extra_columns: Optional[Dict[str, Any]] = None,
    ) -> tuple:
        """Stream CMS data-api/v1 records page-by-page directly to a temp CSV.

        Each page is written to disk immediately and discarded from memory, so
        peak RAM usage is bounded to one page (~2000 rows) regardless of total
        dataset size.

        Args:
            dataset_uuid: CMS dataset UUID from data.cms.gov/data.json catalog.
            max_records: Cap on total rows. None = fetch all.
            filter_params: Optional extra query params for server-side filtering.
            extra_columns: Optional dict of constant columns to inject into every
                row (e.g. {"year": 2023} for multi-year fetches).

        Returns:
            Tuple of (csv_path: str | None, total_count: int).
            csv_path is None when the API returned zero records.
        """
        api_url = f"{_CMS_DATA_API}/{dataset_uuid}/data"
        offset = 0
        total_count = 0
        tmp = None
        writer = None

        logger.info("[%s] Streaming from CMS data-api: %s", self.SOURCE_NAME, api_url)

        try:
            while True:
                remaining = None if max_records is None else max_records - total_count
                if remaining is not None and remaining <= 0:
                    break
                page_size = _CMS_PAGE_SIZE if remaining is None else min(_CMS_PAGE_SIZE, remaining)

                params: Dict[str, Any] = {"size": page_size, "offset": offset}
                if filter_params:
                    params.update(filter_params)

                resp = self.session.get(api_url, params=params, timeout=120)
                resp.raise_for_status()
                page: List[Dict[str, Any]] = resp.json()
                if not page:
                    break

                if extra_columns:
                    for row in page:
                        row.update(extra_columns)

                # Open CSV on first page so we have column names from the API
                if writer is None:
                    tmp = tempfile.NamedTemporaryFile(
                        mode="w",
                        suffix=".csv",
                        prefix=f"cms_{self.SOURCE_NAME}_",
                        delete=False,
                        newline="",
                        encoding="utf-8",
                    )
                    fieldnames = list(page[0].keys())
                    writer = csv.DictWriter(tmp, fieldnames=fieldnames, extrasaction="ignore")
                    writer.writeheader()

                writer.writerows(page)
                total_count += len(page)
                logger.debug(
                    "[%s] Streamed %d rows to CSV (offset=%d, total=%d)",
                    self.SOURCE_NAME, len(page), offset, total_count,
                )

                if len(page) < page_size:
                    break
                offset += page_size

        finally:
            if tmp is not None:
                tmp.close()

        if total_count == 0:
            logger.info("[%s] CMS API returned 0 records", self.SOURCE_NAME)
            return None, 0

        logger.info("[%s] %d total records streamed to %s", self.SOURCE_NAME, total_count, tmp.name)
        return tmp.name, total_count

    def _stream_cms_api_to_db(
        self,
        dataset_uuid: str,
        loader_fn: Callable,
        source_year: int,
        filter_params: Optional[Dict[str, Any]] = None,
        max_records: Optional[int] = None,
        checkpoint_interval: int = 5,
        **loader_kwargs: Any,
    ) -> Tuple[int, int]:
        """Stream CMS API pages directly to DB via loader_fn, with checkpoint/resume.

        Fetches one page (2000 rows) at a time and immediately inserts it via
        loader_fn(rows=page, source_year=source_year, ...). Peak memory usage is
        O(page_size) regardless of total dataset size.

        This replaces the _fetch_cms_api_to_csv + loader(filepath=...) pattern
        which caused OOMKill because the full CSV was loaded into memory by
        pd.read_csv(filepath, dtype=str, low_memory=False).

        Args:
            dataset_uuid: CMS data.cms.gov dataset UUID.
            loader_fn: Loader function that accepts rows=List[Dict] and source_year=int.
            source_year: Calendar/service year for _source_year column.
            filter_params: Optional extra query params for server-side filtering.
            max_records: Cap on total rows to fetch. None = fetch all.
            checkpoint_interval: Save checkpoint every N pages (default 5 = 10k rows).
            **loader_kwargs: Extra kwargs forwarded to loader_fn.

        Returns:
            Tuple of (total_fetched, total_inserted).
        """
        from ..utils.checkpoint import load_checkpoint, save_checkpoint

        cp = load_checkpoint(self.SOURCE_NAME)
        offset = cp.get("offset", 0) if cp else 0
        total_inserted = cp.get("records_inserted", 0) if cp else 0

        if offset > 0:
            logger.info(
                "[%s] resuming from checkpoint offset=%d (%d already inserted)",
                self.SOURCE_NAME, offset, total_inserted,
            )

        api_url = f"{_CMS_DATA_API}/{dataset_uuid}/data"
        total_fetched = 0
        pages_since_checkpoint = 0

        while True:
            current_offset = offset + total_fetched
            remaining = None if max_records is None else max_records - current_offset
            if remaining is not None and remaining <= 0:
                break
            page_size = _CMS_PAGE_SIZE if remaining is None else min(_CMS_PAGE_SIZE, remaining)

            params: Dict[str, Any] = {"size": page_size, "offset": current_offset}
            if filter_params:
                params.update(filter_params)

            try:
                resp = self.session.get(api_url, params=params, timeout=120)
                resp.raise_for_status()
            except Exception as exc:
                save_checkpoint(self.SOURCE_NAME, {
                    "offset": current_offset,
                    "records_inserted": total_inserted,
                })
                raise

            page: List[Dict[str, Any]] = resp.json()
            if not page:
                break

            source_hash = f"api_stream_{source_year}"
            result = loader_fn(
                rows=page,
                source_year=source_year,
                source_hash=source_hash,
                **loader_kwargs,
            )
            inserted = result.get("records_inserted", 0)
            total_inserted += inserted
            total_fetched += len(page)
            pages_since_checkpoint += 1

            logger.info(
                "[%s] offset=%d fetched=%d inserted=%d (total_fetched=%d total_inserted=%d)",
                self.SOURCE_NAME, current_offset, len(page), inserted,
                offset + total_fetched, total_inserted,
            )

            if pages_since_checkpoint >= checkpoint_interval:
                save_checkpoint(self.SOURCE_NAME, {
                    "offset": offset + total_fetched,
                    "records_inserted": total_inserted,
                })
                pages_since_checkpoint = 0
                logger.info(
                    "[%s] checkpoint saved offset=%d total_inserted=%d",
                    self.SOURCE_NAME, offset + total_fetched, total_inserted,
                )

            if len(page) < page_size:
                break

            import time as _time
            _time.sleep(0.05)

        return offset + total_fetched, total_inserted

    def _stream_cms_api_multi_year_to_db(
        self,
        parent_uuid: str,
        loader_fn: "Callable",
        years: "List[int]",
        max_records_per_year: "Optional[int]" = None,
        filter_params: "Optional[Dict[str, Any]]" = None,
    ) -> "Tuple[int, int]":
        """Stream CMS data for multiple service years directly to DB.

        Discovers per-year dataset UUIDs from the CMS DCAT catalog, then streams
        each year individually via _stream_cms_api_to_db. Clears the checkpoint
        before each year so per-year offsets don't bleed across years.

        Returns:
            Tuple of (total_fetched, total_inserted).
        """
        from ..downloaders.cms_downloader import discover_year_uuids
        from ..utils.checkpoint import clear_checkpoint

        year_uuids = discover_year_uuids(parent_uuid)
        total_fetched = 0
        total_inserted = 0

        for year in sorted(years):
            uuid = year_uuids.get(year)
            if uuid is None:
                logger.warning(
                    "[%s] No sub-UUID found for year=%d (parent=%s) — skipping",
                    self.SOURCE_NAME, year, parent_uuid,
                )
                continue
            logger.info(
                "[%s] Streaming year=%d (UUID=%s...)", self.SOURCE_NAME, year, uuid[:8]
            )
            clear_checkpoint(self.SOURCE_NAME)
            try:
                fetched, inserted = self._stream_cms_api_to_db(
                    uuid,
                    loader_fn,
                    source_year=year,
                    max_records=max_records_per_year,
                    filter_params=filter_params,
                )
                total_fetched += fetched
                total_inserted += inserted
            except Exception as exc:
                logger.warning(
                    "[%s] Failed to stream year=%d: %s — skipping", self.SOURCE_NAME, year, exc
                )

        return total_fetched, total_inserted

    def _stream_open_payments_to_db(
        self,
        loader_fn: Callable,
        source_year: int,
        dataset_uuid: str = "e6b17c6a-2534-4207-a4a1-6746a14911ff",
        max_records: Optional[int] = None,
        checkpoint_interval: int = 20,
    ) -> Tuple[int, int]:
        """Stream Open Payments DKAN API pages to DB with checkpoint/resume.

        Uses the openpaymentsdata.cms.gov DKAN endpoint (different from data.cms.gov).

        Returns:
            Tuple of (total_fetched, total_inserted).
        """
        from ..utils.checkpoint import load_checkpoint, save_checkpoint

        _DKAN_PAGE_SIZE = 500
        _OPEN_PAYMENTS_API = "https://openpaymentsdata.cms.gov/api/1/datastore/query"

        cp = load_checkpoint(self.SOURCE_NAME)
        offset = cp.get("offset", 0) if cp else 0
        total_inserted = cp.get("records_inserted", 0) if cp else 0

        if offset > 0:
            logger.info(
                "[%s] resuming from checkpoint offset=%d (%d already inserted)",
                self.SOURCE_NAME, offset, total_inserted,
            )

        api_url = f"{_OPEN_PAYMENTS_API}/{dataset_uuid}/0"
        total_fetched = 0
        pages_since_checkpoint = 0

        while True:
            current_offset = offset + total_fetched
            remaining = None if max_records is None else max_records - current_offset
            if remaining is not None and remaining <= 0:
                break
            page_size = _DKAN_PAGE_SIZE if remaining is None else min(_DKAN_PAGE_SIZE, remaining)

            try:
                resp = self.session.get(
                    api_url,
                    params={"offset": current_offset, "limit": page_size, "keys": "true"},
                    timeout=60,
                )
                resp.raise_for_status()
            except Exception as exc:
                save_checkpoint(self.SOURCE_NAME, {
                    "offset": current_offset,
                    "records_inserted": total_inserted,
                })
                raise

            data = resp.json()
            page: List[Dict[str, Any]] = data.get("results", [])
            if not page:
                break

            source_hash = f"api_stream_{source_year}"
            result = loader_fn(
                rows=page,
                source_year=source_year,
                source_hash=source_hash,
            )
            inserted = result.get("records_inserted", 0)
            total_inserted += inserted
            total_fetched += len(page)
            pages_since_checkpoint += 1

            logger.info(
                "[%s] offset=%d fetched=%d inserted=%d (total_fetched=%d total_inserted=%d)",
                self.SOURCE_NAME, current_offset, len(page), inserted,
                offset + total_fetched, total_inserted,
            )

            if pages_since_checkpoint >= checkpoint_interval:
                save_checkpoint(self.SOURCE_NAME, {
                    "offset": offset + total_fetched,
                    "records_inserted": total_inserted,
                })
                pages_since_checkpoint = 0

            if len(page) < page_size:
                break

            import time as _time
            _time.sleep(0.05)

        return offset + total_fetched, total_inserted

    def _fetch_cms_api(
        self,
        dataset_uuid: str,
        max_records: Optional[int] = None,
        filter_params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch records from the CMS data-api/v1 streaming endpoint.

        .. deprecated::
            Use _fetch_cms_api_to_csv() instead to avoid accumulating all rows
            in memory. This method is retained for any callers that genuinely
            need the full list (e.g. unit tests, small datasets).

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

            resp = self.session.get(api_url, params=params, timeout=120)
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

    def _fetch_cms_api_multi_year(
        self,
        parent_uuid: str,
        years: List[int],
        max_records_per_year: Optional[int] = None,
        filter_params: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Fetch CMS records for multiple service years using dynamic UUID discovery.

        Discovers year-specific dataset UUIDs from the CMS DCAT catalog (cached 24h),
        then fetches each year separately.  Injects a ``year`` column into every record
        so the orchestrator's auto-detection logic passes the correct ``source_year``
        to the loader.

        Falls back to ``parent_uuid`` for any year whose sub-UUID cannot be found
        (with a warning — this means all such years will share the same data).

        Args:
            parent_uuid: The canonical dataset UUID from CMS_DATASET_REGISTRY.
            years: Service years to fetch (e.g. [2021, 2022, 2023]).
            max_records_per_year: Cap per year; None = fetch all.
            filter_params: Optional extra query params (e.g. provider type filter).

        Returns:
            List of paths to per-year temp CSV files.
            Each file contains records for one service year with a ``year`` column.
        """
        from ..downloaders.cms_downloader import discover_year_uuids

        year_uuids = discover_year_uuids(parent_uuid)

        csv_paths: List[str] = []
        for year in sorted(years):
            uuid = year_uuids.get(year)
            if uuid is None:
                logger.warning(
                    "[%s] No sub-UUID found in CMS catalog for year=%d (parent=%s) — skipping year",
                    self.SOURCE_NAME, year, parent_uuid,
                )
                continue

            logger.info(
                "[%s] Fetching year=%d (UUID=%s...)", self.SOURCE_NAME, year, uuid[:8]
            )
            try:
                path, count = self._fetch_cms_api_to_csv(
                    uuid, max_records_per_year, filter_params,
                    extra_columns={"year": year},
                )
            except Exception as exc:
                logger.warning(
                    "[%s] Failed to fetch year=%d: %s — skipping", self.SOURCE_NAME, year, exc
                )
                continue

            if not path:
                logger.info("[%s] year=%d returned 0 records", self.SOURCE_NAME, year)
                continue

            csv_paths.append(path)
            logger.info("[%s] year=%d: %d records → %s", self.SOURCE_NAME, year, count, path)

        return csv_paths

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
