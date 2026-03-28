"""CMS Hospital General Information Fetcher.

Feature: 001-data-layer-postgrest-gitops
Task: CMS Data Access Strategy Implementation

Fetches hospital demographics, ownership, and quality ratings.
Uses the CMS catalog service for dynamic dataset discovery.

Source: https://data.cms.gov/provider-data/topics/hospitals
"""

import logging
from datetime import datetime
from typing import Any, Optional

from .base import BaseFetcher
from ..services.cms_catalog import (
    CMSCatalogService,
    get_cms_catalog,
    fetch_with_fallback,
)

logger = logging.getLogger(__name__)


class CMSHospitalInfoFetcher(BaseFetcher):
    """Fetcher for CMS Hospital General Information data."""

    SOURCE_NAME = "cms_hospital_info"
    BASE_URL = "https://data.cms.gov/provider-data"

    # Dataset search terms for catalog lookup
    # Note: Hospital General Info is in provider-data portal, not main data.cms.gov
    DATASET_TITLE = "Hospital General Information"
    DATASET_TITLE_ALT = "Provider Data Catalog"

    # Provider-data portal API endpoints (different from data.cms.gov)
    PROVIDER_DATA_API = "https://data.cms.gov/provider-data/api/1/datastore/query"

    # Legacy dataset identifiers (fallback)
    HOSPITAL_INFO_DATASET = "xubh-q36u"

    # Known working download URLs (updated 2026-01-15)
    KNOWN_CSV_URLS = [
        "https://data.cms.gov/provider-data/sites/default/files/resources/893c372430d9d71a1c52737d01239d47_1760630721/Hospital_General_Information.csv",
        "https://data.cms.gov/provider-data/dataset/xubh-q36u/data.csv",
    ]

    # Provider Data API for discovering latest URLs
    PROVIDER_DATA_METASTORE = "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items"

    def __init__(self, data_dir: Optional[str] = None):
        """
        Initialize the CMS Hospital Info fetcher.

        Args:
            data_dir: Directory to store downloaded files.
        """
        super().__init__(data_dir)
        self._catalog: Optional[CMSCatalogService] = None

    @property
    def catalog(self) -> CMSCatalogService:
        """Get the CMS catalog service (lazy initialization)."""
        if self._catalog is None:
            self._catalog = get_cms_catalog()
        return self._catalog

    def get_latest_url(self) -> str:
        """Get URL for the latest hospital info data using catalog lookup."""
        dataset_info = self.catalog.get_dataset_by_title(self.DATASET_TITLE)

        if dataset_info:
            # Prefer CSV download URL
            csv_url = dataset_info.get_csv_url()
            if csv_url:
                return csv_url

            # Fallback to API endpoint
            if dataset_info.identifier:
                return self.catalog.get_api_endpoint(dataset_info.identifier)

        # Legacy fallback
        logger.warning("Dataset not found in catalog, using legacy URL")
        return f"https://data.cms.gov/provider-data/api/1/datastore/query/{self.HOSPITAL_INFO_DATASET}/0"

    def fetch(self, **kwargs) -> dict[str, Any]:
        """
        Fetch CMS Hospital General Information.

        Uses a multi-method fallback strategy:
        1. Try known working CSV URLs (provider-data portal)
        2. Try catalog-based discovery
        3. Try legacy API endpoints

        Returns:
            Fetch result dictionary with status, filepath, records, hash.
        """
        try:
            logger.info("Fetching CMS Hospital General Information")

            # Method 1: Try known working CSV URLs first
            result = self._fetch_known_csv()
            if result.get('status') == 'success':
                return result

            # Method 2: Try catalog-based fetch with fallback
            logger.info("Trying catalog-based discovery")
            catalog_result = fetch_with_fallback(
                dataset_title=self.DATASET_TITLE,
                catalog=self.catalog
            )

            if catalog_result.get('status') == 'success':
                return self._process_fetch_result(catalog_result)

            # Method 3: Try legacy API methods
            logger.warning("Catalog fetch failed, trying legacy methods")
            return self._fetch_legacy()

        except Exception as e:
            logger.exception(f"Failed to fetch CMS Hospital Info: {e}")
            result = {
                'status': 'failed',
                'error': str(e),
            }
            self.log_fetch_result(result)
            return result

    def _process_fetch_result(self, result: dict) -> dict[str, Any]:
        """
        Process the fetch result and save to file.

        Args:
            result: Result from fetch_with_fallback.

        Returns:
            Processed result dictionary.
        """
        import json

        method = result.get('method', 'unknown')
        timestamp = datetime.now().strftime('%Y%m%d')

        if method == 'csv_download':
            # Save CSV content
            filename = f"cms_hospital_info_{timestamp}.csv"
            filepath = self.data_dir / filename

            with open(filepath, 'wb') as f:
                f.write(result.get('content', b''))

            # Count records
            import pandas as pd
            try:
                df = pd.read_csv(filepath, dtype={
                    'Facility_ID': str, 'ZIP_Code': str,   # underscore format
                    'Facility ID': str, 'ZIP Code': str,   # space format
                })
                record_count = len(df)
            except Exception as e:
                logger.warning(f"Could not count records: {e}")
                record_count = None

            final_result = {
                'status': 'success',
                'filepath': str(filepath),
                'records': record_count,
                'hash': self.calculate_hash(filepath),
                'method': 'csv_download',
            }

        elif method == 'api_paginated':
            # Save JSON data
            data = result.get('data', [])
            filename = f"cms_hospital_info_{timestamp}.json"
            filepath = self.data_dir / filename

            with open(filepath, 'w') as f:
                json.dump(data, f)

            final_result = {
                'status': 'success',
                'filepath': str(filepath),
                'records': len(data),
                'hash': self.calculate_hash(filepath),
                'method': 'api_paginated',
            }

        elif method == 'zip_download':
            # Save and extract ZIP
            import zipfile
            import io

            zip_filename = f"cms_hospital_info_{timestamp}.zip"
            zip_filepath = self.data_dir / zip_filename

            with open(zip_filepath, 'wb') as f:
                f.write(result.get('content', b''))

            # Extract CSV from ZIP
            extracted_files = []
            with zipfile.ZipFile(io.BytesIO(result.get('content', b''))) as zf:
                for name in zf.namelist():
                    if name.endswith('.csv'):
                        zf.extract(name, self.data_dir)
                        extracted_files.append(str(self.data_dir / name))

            final_result = {
                'status': 'success',
                'filepath': extracted_files[0] if extracted_files else str(zip_filepath),
                'zip_file': str(zip_filepath),
                'extracted_files': extracted_files,
                'method': 'zip_download',
            }

        else:
            final_result = {
                'status': 'failed',
                'error': f"Unknown method: {method}",
            }

        self.log_fetch_result(final_result)
        return final_result

    def _discover_csv_url(self) -> Optional[str]:
        """
        Discover the latest CSV URL from the provider-data metastore.

        Returns:
            CSV download URL or None if discovery fails.
        """
        try:
            logger.info("Discovering CSV URL from provider-data metastore")
            response = self.session.get(self.PROVIDER_DATA_METASTORE, timeout=30)
            response.raise_for_status()
            datasets = response.json()

            for ds in datasets:
                if ds.get('identifier') == self.HOSPITAL_INFO_DATASET:
                    # Found the dataset, extract download URL
                    distribution = ds.get('distribution', [])
                    for dist in distribution:
                        if dist.get('format', '').lower() == 'csv':
                            url = dist.get('downloadURL')
                            if url:
                                logger.info(f"Discovered CSV URL: {url}")
                                return url
            return None
        except Exception as e:
            logger.warning(f"Failed to discover CSV URL: {e}")
            return None

    def _fetch_known_csv(self) -> dict[str, Any]:
        """
        Try fetching from known working CSV URLs.

        The Hospital General Information dataset is in the provider-data portal
        which has different URLs than the main data.cms.gov catalog.

        Returns:
            Fetch result dictionary.
        """
        import pandas as pd

        # Try to discover the latest URL first
        discovered_url = self._discover_csv_url()
        urls_to_try = [discovered_url] if discovered_url else []
        urls_to_try.extend(self.KNOWN_CSV_URLS)

        for csv_url in urls_to_try:
            if not csv_url:
                continue
            try:
                logger.info(f"Trying known CSV URL: {csv_url}")

                response = self.session.get(csv_url, timeout=120, stream=True)
                response.raise_for_status()

                # Verify it's CSV, not HTML error page
                content_type = response.headers.get('content-type', '')
                if 'html' in content_type.lower():
                    logger.warning(f"Got HTML instead of CSV from {csv_url}")
                    continue

                # Save to file
                timestamp = datetime.now().strftime('%Y%m%d')
                filename = f"cms_hospital_info_{timestamp}.csv"
                filepath = self.data_dir / filename

                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                # Verify and count records
                df = pd.read_csv(filepath, dtype={
                    'Facility_ID': str, 'ZIP_Code': str,   # underscore format
                    'Facility ID': str, 'ZIP Code': str,   # space format
                })

                result = {
                    'status': 'success',
                    'filepath': str(filepath),
                    'records': len(df),
                    'hash': self.calculate_hash(filepath),
                    'method': 'known_csv',
                }
                self.log_fetch_result(result)
                return result

            except Exception as e:
                logger.warning(f"Known CSV URL failed: {csv_url} - {e}")
                continue

        return {'status': 'failed', 'error': 'All known CSV URLs failed'}

    def _fetch_legacy(self) -> dict[str, Any]:
        """
        Legacy fetch method using hardcoded URLs.

        Fallback for when catalog-based fetch fails.

        Returns:
            Fetch result dictionary.
        """
        try:
            logger.info("Attempting legacy API fetch")

            # Try API first
            api_url = f"https://data.cms.gov/provider-data/api/1/datastore/query/{self.HOSPITAL_INFO_DATASET}/0"
            params = {'limit': 10000, 'offset': 0}
            all_records = []

            try:
                while True:
                    response = self.session.get(api_url, params=params, timeout=120)
                    response.raise_for_status()
                    data = response.json()

                    results = data.get('results', [])
                    if not results:
                        break

                    all_records.extend(results)

                    if len(results) < params['limit']:
                        break

                    params['offset'] += params['limit']

                    if params['offset'] > 100000:
                        logger.warning("Hit safety limit")
                        break

            except Exception as api_error:
                logger.warning(f"API fetch failed: {api_error}, trying CSV download")
                return self._fetch_csv_legacy()

            if all_records:
                import json
                filename = f"cms_hospital_info_{datetime.now().strftime('%Y%m%d')}.json"
                filepath = self.data_dir / filename

                with open(filepath, 'w') as f:
                    json.dump(all_records, f)

                result = {
                    'status': 'success',
                    'filepath': str(filepath),
                    'records': len(all_records),
                    'hash': self.calculate_hash(filepath),
                    'method': 'legacy_api',
                }
            else:
                result = self._fetch_csv_legacy()

            self.log_fetch_result(result)
            return result

        except Exception as e:
            logger.exception(f"Legacy fetch failed: {e}")
            return {
                'status': 'failed',
                'error': str(e),
            }

    def _fetch_csv_legacy(self) -> dict[str, Any]:
        """
        Download CSV directly using legacy URLs.

        Returns:
            Fetch result dictionary.
        """
        import pandas as pd

        legacy_urls = [
            "https://data.cms.gov/provider-data/dataset/xubh-q36u/data.csv",
            "https://data.cms.gov/provider-data/sites/default/files/resources/092256becd267d9eeccf73bf7d16c46b_1704412525/Hospital_General_Information.csv",
        ]

        for csv_url in legacy_urls:
            try:
                logger.info(f"Trying legacy CSV URL: {csv_url}")
                filename = f"cms_hospital_info_{datetime.now().strftime('%Y%m%d')}.csv"
                filepath = self.download_file(csv_url, filename)

                # Verify it's actually CSV
                df = pd.read_csv(filepath, dtype={
                    'Facility_ID': str, 'ZIP_Code': str,   # underscore format
                    'Facility ID': str, 'ZIP Code': str,   # space format
                })

                return {
                    'status': 'success',
                    'filepath': str(filepath),
                    'records': len(df),
                    'hash': self.calculate_hash(filepath),
                    'method': 'legacy_csv',
                }

            except Exception as e:
                logger.warning(f"Legacy CSV URL failed: {e}")
                continue

        return {
            'status': 'failed',
            'error': "All legacy CSV URLs failed",
        }

    def get_api_endpoints(self) -> dict[str, str]:
        """Return available API endpoints for hospital data."""
        endpoints = {
            'legacy_api': f"https://data.cms.gov/provider-data/api/1/datastore/query/{self.HOSPITAL_INFO_DATASET}/0",
            'legacy_csv': "https://data.cms.gov/provider-data/dataset/xubh-q36u/data.csv",
        }

        # Add catalog-discovered endpoints
        dataset_info = self.catalog.get_dataset_by_title(self.DATASET_TITLE)
        if dataset_info:
            endpoints['catalog_identifier'] = dataset_info.identifier
            endpoints['catalog_modified'] = dataset_info.modified
            csv_url = dataset_info.get_csv_url()
            if csv_url:
                endpoints['catalog_csv'] = csv_url
            api_url = dataset_info.get_api_url()
            if api_url:
                endpoints['catalog_api'] = api_url

        return endpoints
