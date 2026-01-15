"""CMS Data Catalog Service.

Feature: 001-data-layer-postgrest-gitops
Task: CMS Data Access Strategy Implementation

Provides dynamic dataset discovery using the CMS data.json catalog.
Reference: https://data.cms.gov/data.json (DCAT format)
"""

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# CMS Catalog URL (DCAT format)
CMS_CATALOG_URL = "https://data.cms.gov/data.json"

# Cache settings
DEFAULT_CACHE_DIR = "/tmp/cms_catalog"
CACHE_TTL_HOURS = 24


@dataclass
class DatasetDistribution:
    """Represents a dataset distribution (download format)."""
    media_type: str
    download_url: str
    title: str
    description: str = ""
    format: str = ""
    access_url: str = ""


@dataclass
class DatasetInfo:
    """Represents a CMS dataset from the catalog."""
    identifier: str
    title: str
    description: str
    modified: str
    distributions: list[DatasetDistribution]
    keyword: list[str]
    publisher: str = ""
    landing_page: str = ""

    def get_csv_url(self) -> Optional[str]:
        """Get CSV download URL if available."""
        for dist in self.distributions:
            if 'csv' in dist.media_type.lower() or dist.format.lower() == 'csv':
                return dist.download_url or dist.access_url
        return None

    def get_zip_url(self) -> Optional[str]:
        """Get ZIP download URL if available."""
        for dist in self.distributions:
            if 'zip' in dist.media_type.lower() or dist.format.lower() == 'zip':
                return dist.download_url or dist.access_url
        return None

    def get_api_url(self) -> Optional[str]:
        """Get API endpoint URL if available."""
        for dist in self.distributions:
            if 'api' in dist.title.lower() or 'json' in dist.media_type.lower():
                return dist.access_url or dist.download_url
        return None


class CMSCatalogService:
    """
    Service for discovering and accessing CMS datasets via the data catalog.

    Uses the CMS data.json (DCAT format) to dynamically discover:
    - Dataset identifiers (UUIDs)
    - Distribution URLs (CSV, ZIP, API endpoints)
    - Last modified dates
    - Schema information

    Example usage:
        catalog = CMSCatalogService()
        dataset = catalog.get_dataset_by_title("Hospital General Information")
        csv_url = dataset.get_csv_url()
    """

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        cache_ttl_hours: int = CACHE_TTL_HOURS
    ):
        """
        Initialize the CMS Catalog Service.

        Args:
            cache_dir: Directory for caching the catalog. Defaults to /tmp/cms_catalog
            cache_ttl_hours: Hours before cache expires. Defaults to 24.
        """
        self.cache_dir = Path(cache_dir or os.environ.get('CMS_CACHE_DIR', DEFAULT_CACHE_DIR))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.cache_file = self.cache_dir / "data.json"

        # Session with retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.headers.update({
            'User-Agent': 'TAVR-Data-Platform/1.0 (Edwards Medical; Data Integration)',
            'Accept': 'application/json',
        })

        self._catalog_data: Optional[dict] = None

    def _is_cache_valid(self) -> bool:
        """Check if the cached catalog is still valid."""
        if not self.cache_file.exists():
            return False

        cache_age = datetime.now() - datetime.fromtimestamp(self.cache_file.stat().st_mtime)
        return cache_age < self.cache_ttl

    def _load_from_cache(self) -> Optional[dict]:
        """Load catalog from cache file."""
        try:
            with open(self.cache_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load catalog from cache: {e}")
            return None

    def _save_to_cache(self, data: dict) -> None:
        """Save catalog to cache file."""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(data, f)
            logger.debug(f"Saved catalog to cache: {self.cache_file}")
        except Exception as e:
            logger.warning(f"Failed to save catalog to cache: {e}")

    def fetch_catalog(self, force_refresh: bool = False) -> dict:
        """
        Fetch the CMS data catalog.

        Args:
            force_refresh: If True, bypass cache and fetch fresh data.

        Returns:
            The catalog data as a dictionary.
        """
        # Check cache first
        if not force_refresh and self._is_cache_valid():
            cached = self._load_from_cache()
            if cached:
                logger.debug("Using cached CMS catalog")
                self._catalog_data = cached
                return cached

        # Fetch from CMS
        logger.info(f"Fetching CMS catalog from {CMS_CATALOG_URL}")
        try:
            response = self.session.get(CMS_CATALOG_URL, timeout=60)
            response.raise_for_status()
            data = response.json()

            self._save_to_cache(data)
            self._catalog_data = data

            dataset_count = len(data.get('dataset', []))
            logger.info(f"Fetched CMS catalog with {dataset_count} datasets")

            return data

        except Exception as e:
            logger.error(f"Failed to fetch CMS catalog: {e}")
            # Try to use stale cache as fallback
            cached = self._load_from_cache()
            if cached:
                logger.warning("Using stale cache as fallback")
                self._catalog_data = cached
                return cached
            raise

    def get_datasets(self, force_refresh: bool = False) -> list[dict]:
        """
        Get all datasets from the catalog.

        Args:
            force_refresh: If True, bypass cache.

        Returns:
            List of dataset dictionaries.
        """
        catalog = self.fetch_catalog(force_refresh)
        return catalog.get('dataset', [])

    def search_datasets(
        self,
        query: str,
        force_refresh: bool = False
    ) -> list[DatasetInfo]:
        """
        Search for datasets by title or keyword.

        Args:
            query: Search term to match in title or keywords.
            force_refresh: If True, bypass cache.

        Returns:
            List of matching DatasetInfo objects.
        """
        datasets = self.get_datasets(force_refresh)
        query_lower = query.lower()
        results = []

        for ds in datasets:
            title = ds.get('title', '').lower()
            description = ds.get('description', '').lower()
            keywords = [k.lower() for k in ds.get('keyword', [])]

            if (query_lower in title or
                query_lower in description or
                any(query_lower in kw for kw in keywords)):
                results.append(self._parse_dataset(ds))

        return results

    def get_dataset_by_title(
        self,
        title: str,
        exact_match: bool = False,
        force_refresh: bool = False
    ) -> Optional[DatasetInfo]:
        """
        Get a dataset by its title.

        Args:
            title: Dataset title to search for.
            exact_match: If True, require exact title match.
            force_refresh: If True, bypass cache.

        Returns:
            DatasetInfo if found, None otherwise.
        """
        datasets = self.get_datasets(force_refresh)
        title_lower = title.lower()

        for ds in datasets:
            ds_title = ds.get('title', '').lower()

            if exact_match:
                if ds_title == title_lower:
                    return self._parse_dataset(ds)
            else:
                if title_lower in ds_title:
                    return self._parse_dataset(ds)

        return None

    def get_dataset_by_identifier(
        self,
        identifier: str,
        force_refresh: bool = False
    ) -> Optional[DatasetInfo]:
        """
        Get a dataset by its identifier (UUID).

        Args:
            identifier: Dataset UUID/identifier.
            force_refresh: If True, bypass cache.

        Returns:
            DatasetInfo if found, None otherwise.
        """
        datasets = self.get_datasets(force_refresh)

        for ds in datasets:
            if ds.get('identifier') == identifier:
                return self._parse_dataset(ds)

        return None

    def _parse_dataset(self, raw: dict) -> DatasetInfo:
        """Parse a raw dataset dict into DatasetInfo."""
        distributions = []
        for dist in raw.get('distribution', []):
            distributions.append(DatasetDistribution(
                media_type=dist.get('mediaType', ''),
                download_url=dist.get('downloadURL', ''),
                access_url=dist.get('accessURL', ''),
                title=dist.get('title', ''),
                description=dist.get('description', ''),
                format=dist.get('format', ''),
            ))

        return DatasetInfo(
            identifier=raw.get('identifier', ''),
            title=raw.get('title', ''),
            description=raw.get('description', ''),
            modified=raw.get('modified', ''),
            distributions=distributions,
            keyword=raw.get('keyword', []),
            publisher=raw.get('publisher', {}).get('name', ''),
            landing_page=raw.get('landingPage', ''),
        )

    def get_api_endpoint(self, dataset_id: str) -> str:
        """
        Construct the CMS Data API endpoint for a dataset.

        Args:
            dataset_id: The dataset UUID.

        Returns:
            API endpoint URL.
        """
        return f"https://data.cms.gov/data-api/v1/dataset/{dataset_id}/data"

    def get_data_viewer_endpoint(self, dataset_id: str) -> str:
        """
        Construct the CMS Data Viewer API endpoint.

        Args:
            dataset_id: The dataset UUID.

        Returns:
            Data viewer endpoint URL.
        """
        return f"https://data.cms.gov/data-api/v1/dataset/{dataset_id}/data-viewer"


# Module-level singleton
_catalog_service: Optional[CMSCatalogService] = None


def get_cms_catalog(
    cache_dir: Optional[str] = None,
    cache_ttl_hours: int = CACHE_TTL_HOURS
) -> CMSCatalogService:
    """
    Get the singleton CMS catalog service instance.

    Args:
        cache_dir: Directory for caching. Only used on first call.
        cache_ttl_hours: Cache TTL in hours. Only used on first call.

    Returns:
        The CMS catalog service instance.
    """
    global _catalog_service
    if _catalog_service is None:
        _catalog_service = CMSCatalogService(cache_dir, cache_ttl_hours)
    return _catalog_service


def fetch_cms_api_paginated(
    dataset_id: str,
    filters: Optional[dict] = None,
    max_records: int = 1_000_000,
    delay_ms: int = 100
) -> list[dict]:
    """
    Fetch data from CMS API with pagination.

    Implements the recommended approach from the CMS data access strategy.

    Args:
        dataset_id: The dataset UUID.
        filters: Optional field filters.
        max_records: Maximum records to fetch (safety limit).
        delay_ms: Delay between requests in milliseconds.

    Returns:
        List of all records.
    """
    base_url = f"https://data.cms.gov/data-api/v1/dataset/{dataset_id}/data"
    size = 5000  # Maximum allowed
    offset = 0
    all_records = []

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'TAVR-Data-Platform/1.0',
        'Accept': 'application/json',
    })

    while True:
        params = {'size': size, 'offset': offset}
        if filters:
            for key, value in filters.items():
                params[f'filter[{key}]'] = value

        logger.debug(f"Fetching CMS API: offset={offset}")
        response = session.get(base_url, params=params, timeout=120)

        if response.status_code != 200:
            logger.warning(f"CMS API returned {response.status_code}")
            break

        data = response.json()
        records = data if isinstance(data, list) else data.get('data', [])

        if not records:
            break

        all_records.extend(records)
        offset += size

        # Safety limit
        if offset >= max_records:
            logger.warning(f"Hit safety limit of {max_records} records")
            break

        # Rate limiting
        if delay_ms > 0:
            time.sleep(delay_ms / 1000)

    logger.info(f"Fetched {len(all_records)} records from CMS API")
    return all_records


def fetch_with_fallback(
    dataset_title: str,
    catalog: Optional[CMSCatalogService] = None,
    filters: Optional[dict] = None
) -> dict:
    """
    Fetch data using multiple methods with fallback.

    Implements the fallback strategy from the CMS data access document:
    1. Try bulk CSV download
    2. Try API with pagination
    3. Try ZIP download

    Args:
        dataset_title: The dataset title to search for.
        catalog: Optional catalog service (uses singleton if not provided).
        filters: Optional filters for API fetch.

    Returns:
        Dictionary with 'status', 'data' or 'filepath', 'records', 'method'.

    Raises:
        DataFetchError: If all methods fail.
    """
    cat = catalog or get_cms_catalog()
    dataset_info = cat.get_dataset_by_title(dataset_title)

    if not dataset_info:
        return {
            'status': 'failed',
            'error': f"Dataset not found in catalog: {dataset_title}",
        }

    # Method 1: Try bulk CSV download
    csv_url = dataset_info.get_csv_url()
    if csv_url:
        try:
            logger.info(f"Trying CSV download: {csv_url}")
            response = requests.get(csv_url, timeout=300, stream=True)
            response.raise_for_status()

            # Check if response is actually CSV (not HTML error page)
            content_type = response.headers.get('content-type', '')
            if 'html' in content_type.lower():
                raise ValueError("Received HTML instead of CSV")

            return {
                'status': 'success',
                'method': 'csv_download',
                'url': csv_url,
                'content': response.content,
                'content_type': content_type,
            }
        except Exception as e:
            logger.warning(f"CSV download failed: {e}")

    # Method 2: Try API with pagination
    if dataset_info.identifier:
        try:
            logger.info(f"Trying API fetch: {dataset_info.identifier}")
            records = fetch_cms_api_paginated(dataset_info.identifier, filters)

            if records:
                return {
                    'status': 'success',
                    'method': 'api_paginated',
                    'data': records,
                    'records': len(records),
                }
        except Exception as e:
            logger.warning(f"API fetch failed: {e}")

    # Method 3: Try ZIP download
    zip_url = dataset_info.get_zip_url()
    if zip_url:
        try:
            logger.info(f"Trying ZIP download: {zip_url}")
            response = requests.get(zip_url, timeout=600, stream=True)
            response.raise_for_status()

            return {
                'status': 'success',
                'method': 'zip_download',
                'url': zip_url,
                'content': response.content,
            }
        except Exception as e:
            logger.warning(f"ZIP download failed: {e}")

    return {
        'status': 'failed',
        'error': f"All fetch methods failed for {dataset_title}",
        'dataset_info': {
            'identifier': dataset_info.identifier,
            'modified': dataset_info.modified,
            'distributions': len(dataset_info.distributions),
        },
    }
