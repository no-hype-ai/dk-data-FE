"""CMS Medicare Inpatient Hospital Data Fetcher.

Feature: 001-data-layer-postgrest-gitops
Task: CMS Data Access Strategy Implementation

Fetches TAVR procedure volumes (DRG 266/267) from CMS.
Uses the CMS catalog service for dynamic dataset discovery.

Source: https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals
"""

import logging
from datetime import datetime
from typing import Any, Optional

from .base import BaseFetcher
from ..services.cms_catalog import (
    CMSCatalogService,
    get_cms_catalog,
    fetch_cms_api_paginated,
)

logger = logging.getLogger(__name__)


class CMSInpatientFetcher(BaseFetcher):
    """Fetcher for CMS Medicare Inpatient Hospital data."""

    SOURCE_NAME = "cms_medicare_inpatient"
    BASE_URL = "https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals"

    # Dataset search terms for catalog lookup
    DATASET_TITLE = "Medicare Inpatient Hospitals - by Provider and Service"
    DATASET_TITLE_ALT = "Medicare Inpatient Hospitals"

    # Legacy dataset identifiers
    DATASET_ID = "medicare-inpatient-hospitals-by-provider-and-service"

    # API endpoint for direct data access
    API_BASE = "https://data.cms.gov/data-api/v1/dataset"

    # Available fiscal years (update as new data releases)
    AVAILABLE_YEARS = [2021, 2022, 2023]

    # TAVR DRG codes
    TAVR_DRG_CODES = ['266', '267']

    def __init__(self, data_dir: Optional[str] = None):
        """
        Initialize the CMS Inpatient fetcher.

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
        """Get URL for the latest CMS Inpatient data using catalog lookup."""
        dataset_info = self.catalog.get_dataset_by_title(self.DATASET_TITLE)

        if not dataset_info:
            # Try alternate title
            dataset_info = self.catalog.get_dataset_by_title(self.DATASET_TITLE_ALT)

        if dataset_info:
            # Prefer API endpoint for filtering capability
            if dataset_info.identifier:
                return self.catalog.get_api_endpoint(dataset_info.identifier)

            # Fallback to CSV
            csv_url = dataset_info.get_csv_url()
            if csv_url:
                return csv_url

        # Legacy fallback
        logger.warning("Dataset not found in catalog, using legacy URL")
        return f"{self.API_BASE}/{self.DATASET_ID}/data"

    def get_download_url(self, fiscal_year: Optional[int] = None) -> str:
        """
        Get direct download URL for CSV file.

        Args:
            fiscal_year: Specific fiscal year to download.

        Returns:
            Download URL for CSV file.
        """
        year = fiscal_year or max(self.AVAILABLE_YEARS)
        return f"https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals/medicare-inpatient-hospitals-by-provider-and-service/data?year={year}&_format=csv&headers=display"

    def fetch(self, fiscal_year: Optional[int] = None, filter_tavr: bool = True, **kwargs) -> dict[str, Any]:
        """
        Fetch CMS Medicare Inpatient data.

        Uses the catalog-based approach with fallback:
        1. Try catalog discovery for year-specific CSV
        2. Use API with TAVR DRG filtering
        3. Fall back to legacy methods

        Args:
            fiscal_year: Specific fiscal year (defaults to latest).
            filter_tavr: If True, only fetch TAVR DRG codes (266/267).

        Returns:
            Fetch result dictionary.
        """
        try:
            year = fiscal_year or max(self.AVAILABLE_YEARS)
            logger.info(f"Fetching CMS Medicare Inpatient data for FY{year} via catalog")

            # Method 1: Try year-specific CSV from catalog
            csv_url = self._get_year_specific_csv_url(year)
            if csv_url:
                result = self._fetch_csv_from_url(csv_url, year, filter_tavr)
                if result.get('status') == 'success':
                    return result
                logger.warning(f"Catalog CSV download failed: {result.get('error')}")

            # Method 2: Try API with pagination
            dataset_info = self.catalog.get_dataset_by_title(self.DATASET_TITLE)
            if not dataset_info:
                dataset_info = self.catalog.get_dataset_by_title(self.DATASET_TITLE_ALT)

            dataset_id = dataset_info.identifier if dataset_info else None

            if dataset_id:
                result = self._fetch_via_api(dataset_id, year, filter_tavr)
                if result.get('status') == 'success':
                    return result

            # Method 3: Fallback to legacy methods
            logger.warning("Catalog methods failed, trying legacy methods")
            return self._fetch_legacy(year, filter_tavr)

        except Exception as e:
            logger.exception(f"Failed to fetch CMS Inpatient data: {e}")
            result = {
                'status': 'failed',
                'error': str(e),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_csv_from_url(
        self,
        csv_url: str,
        fiscal_year: int,
        filter_tavr: bool
    ) -> dict[str, Any]:
        """
        Fetch data from a CSV URL with optional TAVR filtering.

        Args:
            csv_url: The CSV URL to download.
            fiscal_year: Fiscal year.
            filter_tavr: Whether to filter for TAVR codes.

        Returns:
            Fetch result dictionary.
        """
        import pandas as pd

        try:
            logger.info(f"Downloading CSV from {csv_url}")

            response = self.session.get(csv_url, timeout=300, stream=True)
            response.raise_for_status()

            # Check for HTML error page
            content_type = response.headers.get('content-type', '')
            if 'html' in content_type.lower():
                return {'status': 'failed', 'error': 'Received HTML instead of CSV'}

            # Save to temp file
            timestamp = datetime.now().strftime('%Y%m%d')
            temp_filename = f"cms_inpatient_full_fy{fiscal_year}_{timestamp}.csv"
            temp_filepath = self.data_dir / temp_filename

            with open(temp_filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Read and filter (use latin-1 encoding for CMS files with special chars)
            try:
                df = pd.read_csv(temp_filepath, dtype={'Rndrng_Prvdr_CCN': str, 'DRG_Cd': str})
            except UnicodeDecodeError:
                df = pd.read_csv(temp_filepath, dtype={'Rndrng_Prvdr_CCN': str, 'DRG_Cd': str}, encoding='latin-1')

            if filter_tavr:
                tavr_df = df[df['DRG_Cd'].isin(self.TAVR_DRG_CODES)]
                filename = f"cms_inpatient_tavr_fy{fiscal_year}_{timestamp}.csv"
                filepath = self.data_dir / filename
                tavr_df.to_csv(filepath, index=False)

                result = {
                    'status': 'success',
                    'filepath': str(filepath),
                    'records': len(tavr_df),
                    'total_records': len(df),
                    'fiscal_year': fiscal_year,
                    'hash': self.calculate_hash(filepath),
                    'method': 'catalog_csv',
                }
            else:
                result = {
                    'status': 'success',
                    'filepath': str(temp_filepath),
                    'records': len(df),
                    'fiscal_year': fiscal_year,
                    'hash': self.calculate_hash(temp_filepath),
                    'method': 'catalog_csv',
                }

            self.log_fetch_result(result)
            return result

        except Exception as e:
            logger.warning(f"CSV download failed: {e}")
            return {'status': 'failed', 'error': str(e)}

    def _get_year_specific_csv_url(self, fiscal_year: int) -> Optional[str]:
        """
        Get the CSV URL for a specific fiscal year from the catalog.

        Args:
            fiscal_year: The fiscal year to get data for.

        Returns:
            CSV URL for the specified year, or None.
        """
        dataset_info = self.catalog.get_dataset_by_title(self.DATASET_TITLE)
        if not dataset_info:
            dataset_info = self.catalog.get_dataset_by_title(self.DATASET_TITLE_ALT)

        if not dataset_info:
            return None

        # Look for CSV distribution matching the fiscal year
        # File patterns: DY{year} for data year, e.g., DY23 for 2023
        year_suffix = str(fiscal_year)[-2:]  # e.g., "23" for 2023

        for dist in dataset_info.distributions:
            if 'csv' in dist.media_type.lower() or dist.format.lower() == 'csv':
                url = dist.download_url or dist.access_url
                # Match patterns like "DY23" or "DY2023"
                if f'DY{year_suffix}' in url or f'DY{fiscal_year}' in url:
                    logger.info(f"Found year-specific CSV URL for FY{fiscal_year}: {url}")
                    return url

        # If no year-specific URL found, return the first CSV
        return dataset_info.get_csv_url()

    def _fetch_via_api(
        self,
        dataset_id: str,
        fiscal_year: int,
        filter_tavr: bool
    ) -> dict[str, Any]:
        """
        Fetch data via CMS API with pagination.

        Args:
            dataset_id: The dataset UUID from catalog.
            fiscal_year: Fiscal year.
            filter_tavr: Whether to filter for TAVR codes.

        Returns:
            Fetch result dictionary.
        """
        import json

        try:
            logger.info(f"Fetching via CMS API: {dataset_id}")

            # Build filters for TAVR DRGs
            filters = {}
            if filter_tavr:
                # CMS API uses JSON:API filter syntax
                # DRG 266: TAVR w/ MCC, DRG 267: TAVR w/o MCC
                filters['DRG_Cd'] = ','.join(self.TAVR_DRG_CODES)

            # Fetch with pagination
            records = fetch_cms_api_paginated(
                dataset_id=dataset_id,
                filters=filters,
                max_records=100_000,
                delay_ms=100
            )

            if not records:
                return {
                    'status': 'failed',
                    'error': 'No records returned from API',
                }

            # Save to file
            timestamp = datetime.now().strftime('%Y%m%d')
            suffix = '_tavr' if filter_tavr else ''
            filename = f"cms_inpatient{suffix}_fy{fiscal_year}_{timestamp}.json"
            filepath = self.data_dir / filename

            with open(filepath, 'w') as f:
                json.dump(records, f)

            result = {
                'status': 'success',
                'filepath': str(filepath),
                'records': len(records),
                'fiscal_year': fiscal_year,
                'hash': self.calculate_hash(filepath),
                'method': 'catalog_api',
            }

            self.log_fetch_result(result)
            return result

        except Exception as e:
            logger.warning(f"API fetch failed: {e}")
            return {
                'status': 'failed',
                'error': str(e),
            }

    def _fetch_legacy(self, fiscal_year: int, filter_tavr: bool) -> dict[str, Any]:
        """
        Legacy fetch using hardcoded API endpoint.

        Args:
            fiscal_year: Fiscal year.
            filter_tavr: Whether to filter for TAVR codes.

        Returns:
            Fetch result dictionary.
        """
        import json

        try:
            api_url = f"{self.API_BASE}/{self.DATASET_ID}/data.json"

            params = {
                'size': 5000,
                'offset': 0,
            }

            if filter_tavr:
                params['filter[DRG_Cd]'] = ','.join(self.TAVR_DRG_CODES)

            all_records = []

            while True:
                logger.debug(f"Fetching page at offset {params['offset']}")
                response = self.session.get(api_url, params=params, timeout=120)

                if response.status_code == 404:
                    logger.warning("API returned 404, trying CSV download")
                    return self._fetch_csv(fiscal_year, filter_tavr)

                response.raise_for_status()
                data = response.json()

                if not data:
                    break

                all_records.extend(data)

                if len(data) < params['size']:
                    break

                params['offset'] += params['size']

                if params['offset'] > 50000:
                    logger.warning("Hit safety limit on pagination")
                    break

            if all_records:
                timestamp = datetime.now().strftime('%Y%m%d')
                suffix = '_tavr' if filter_tavr else ''
                filename = f"cms_inpatient{suffix}_fy{fiscal_year}_{timestamp}.json"
                filepath = self.data_dir / filename

                with open(filepath, 'w') as f:
                    json.dump(all_records, f)

                result = {
                    'status': 'success',
                    'filepath': str(filepath),
                    'records': len(all_records),
                    'fiscal_year': fiscal_year,
                    'hash': self.calculate_hash(filepath),
                    'method': 'legacy_api',
                }
            else:
                result = {
                    'status': 'success',
                    'records': 0,
                    'fiscal_year': fiscal_year,
                    'message': 'No records found',
                }

            self.log_fetch_result(result)
            return result

        except Exception as e:
            logger.warning(f"Legacy API failed: {e}")
            return self._fetch_csv(fiscal_year, filter_tavr)

    def _fetch_csv(self, fiscal_year: int, filter_tavr: bool) -> dict[str, Any]:
        """
        Download full CSV file.

        Args:
            fiscal_year: Fiscal year to download.
            filter_tavr: Whether to filter for TAVR codes.

        Returns:
            Fetch result dictionary.
        """
        import pandas as pd

        try:
            csv_url = self.get_download_url(fiscal_year)
            logger.info(f"Downloading CSV from {csv_url}")

            timestamp = datetime.now().strftime('%Y%m%d')
            filename = f"cms_inpatient_fy{fiscal_year}_{timestamp}.csv"
            filepath = self.download_file(csv_url, filename)

            # Read and optionally filter
            df = pd.read_csv(filepath, dtype={'Rndrng_Prvdr_CCN': str, 'DRG_Cd': str})

            if filter_tavr:
                tavr_df = df[df['DRG_Cd'].isin(self.TAVR_DRG_CODES)]
                tavr_filename = f"cms_inpatient_tavr_fy{fiscal_year}_{timestamp}.csv"
                tavr_filepath = self.data_dir / tavr_filename
                tavr_df.to_csv(tavr_filepath, index=False)

                return {
                    'status': 'success',
                    'filepath': str(tavr_filepath),
                    'records': len(tavr_df),
                    'total_records': len(df),
                    'fiscal_year': fiscal_year,
                    'hash': self.calculate_hash(tavr_filepath),
                    'method': 'csv_download',
                }
            else:
                return {
                    'status': 'success',
                    'filepath': str(filepath),
                    'records': len(df),
                    'fiscal_year': fiscal_year,
                    'hash': self.calculate_hash(filepath),
                    'method': 'csv_download',
                }

        except Exception as e:
            logger.exception(f"CSV download failed: {e}")
            return {
                'status': 'failed',
                'error': str(e),
            }

    def fetch_all_years(self, filter_tavr: bool = True) -> dict[str, Any]:
        """
        Fetch data for all available fiscal years.

        Args:
            filter_tavr: Whether to filter for TAVR codes.

        Returns:
            Combined fetch results.
        """
        results = {}
        total_records = 0

        for year in self.AVAILABLE_YEARS:
            result = self.fetch(fiscal_year=year, filter_tavr=filter_tavr)
            results[year] = result
            if result.get('status') == 'success':
                total_records += result.get('records', 0)

        return {
            'status': 'success',
            'years': results,
            'total_records': total_records,
        }

    def get_api_endpoints(self) -> dict[str, str]:
        """Return available API endpoints for inpatient data."""
        endpoints = {
            'legacy_api': f"{self.API_BASE}/{self.DATASET_ID}/data.json",
            'legacy_csv': self.get_download_url(),
        }

        # Add catalog-discovered endpoints
        dataset_info = self.catalog.get_dataset_by_title(self.DATASET_TITLE)
        if not dataset_info:
            dataset_info = self.catalog.get_dataset_by_title(self.DATASET_TITLE_ALT)

        if dataset_info:
            endpoints['catalog_identifier'] = dataset_info.identifier
            endpoints['catalog_modified'] = dataset_info.modified
            endpoints['catalog_api'] = self.catalog.get_api_endpoint(dataset_info.identifier)
            csv_url = dataset_info.get_csv_url()
            if csv_url:
                endpoints['catalog_csv'] = csv_url

        return endpoints
