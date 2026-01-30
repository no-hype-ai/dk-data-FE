"""CMS Hospital Cost Reports (HCRIS) Fetcher.

Feature: 001-data-layer-postgrest-gitops
Task: CMS Data Access Strategy Implementation

Fetches hospital financial data for financial capacity scoring.
Uses the CMS catalog service for dynamic dataset discovery.

Source: https://www.cms.gov/Research-Statistics-Data-and-Systems/Downloadable-Public-Use-Files/Cost-Reports
Alternative: https://data.cms.gov/provider-compliance/cost-report/hospital-provider-cost-report
"""

import io
import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .base import BaseFetcher
from ..services.cms_catalog import (
    CMSCatalogService,
    get_cms_catalog,
    fetch_with_fallback,
)

logger = logging.getLogger(__name__)


class CMSCostReportsFetcher(BaseFetcher):
    """Fetcher for CMS Hospital Cost Reports (HCRIS) data."""

    SOURCE_NAME = "cms_cost_reports"
    BASE_URL = "https://www.cms.gov/Research-Statistics-Data-and-Systems/Downloadable-Public-Use-Files/Cost-Reports"

    # Dataset search terms for catalog lookup
    DATASET_TITLE = "Hospital Provider Cost Report"
    DATASET_TITLE_ALT = "Hospital Cost Report"

    # Direct download URLs for HCRIS files (legacy)
    HCRIS_BASE = "https://downloads.cms.gov/files/hcris"

    # Alternative: Hospital Provider Cost Report from data.cms.gov
    COST_REPORT_API = "https://data.cms.gov/provider-compliance/cost-report/hospital-provider-cost-report/data"

    # Key report files within the ZIP
    REPORT_FILES = {
        'rpt': 'Report file with provider info and report dates',
        'nmrc': 'Numeric data (costs, revenues, beds)',
        'alpha': 'Alpha data (provider name, address)',
    }

    # Available years
    AVAILABLE_YEARS = [2020, 2021, 2022, 2023]

    def __init__(self, data_dir: Optional[str] = None):
        """
        Initialize the CMS Cost Reports fetcher.

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
        """Get URL for latest cost report data."""
        # Try catalog first
        dataset_info = self.catalog.get_dataset_by_title(self.DATASET_TITLE)
        if not dataset_info:
            dataset_info = self.catalog.get_dataset_by_title(self.DATASET_TITLE_ALT)

        if dataset_info:
            # Prefer ZIP download for cost reports (large dataset)
            zip_url = dataset_info.get_zip_url()
            if zip_url:
                return zip_url

            # CSV if available
            csv_url = dataset_info.get_csv_url()
            if csv_url:
                return csv_url

            # API endpoint
            if dataset_info.identifier:
                return self.catalog.get_api_endpoint(dataset_info.identifier)

        # Legacy fallback
        year = max(self.AVAILABLE_YEARS)
        return f"{self.HCRIS_BASE}/hosp10-{year}-HCRIS.zip"

    def fetch(self, fiscal_year: Optional[int] = None) -> dict[str, Any]:
        """
        Fetch CMS Hospital Cost Reports.

        Uses the catalog-based approach with fallback:
        1. Try catalog discovery for dataset info
        2. Download ZIP or CSV based on availability
        3. Fall back to legacy HCRIS download

        Args:
            fiscal_year: Specific fiscal year (defaults to latest).

        Returns:
            Fetch result dictionary.
        """
        try:
            year = fiscal_year or max(self.AVAILABLE_YEARS)
            logger.info(f"Fetching CMS Cost Reports for FY{year} via catalog")

            # Try catalog-based fetch first
            result = self._fetch_via_catalog(year)
            if result.get('status') == 'success':
                return result

            # Fallback to legacy HCRIS download
            logger.warning("Catalog fetch failed, trying legacy HCRIS download")
            return self._fetch_legacy(year)

        except Exception as e:
            logger.exception(f"Failed to fetch CMS Cost Reports: {e}")
            result = {
                'status': 'failed',
                'error': str(e),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_via_catalog(self, fiscal_year: int) -> dict[str, Any]:
        """
        Fetch cost reports using the catalog service.

        Args:
            fiscal_year: Fiscal year.

        Returns:
            Fetch result dictionary.
        """
        # Try catalog-based fetch with fallback
        result = fetch_with_fallback(
            dataset_title=self.DATASET_TITLE,
            catalog=self.catalog
        )

        if result.get('status') != 'success':
            # Try alternate title
            result = fetch_with_fallback(
                dataset_title=self.DATASET_TITLE_ALT,
                catalog=self.catalog
            )

        if result.get('status') == 'success':
            return self._process_fetch_result(result, fiscal_year)

        return result

    def _process_fetch_result(self, result: dict, fiscal_year: int) -> dict[str, Any]:
        """
        Process the fetch result and save to file.

        Args:
            result: Result from fetch_with_fallback.
            fiscal_year: Fiscal year.

        Returns:
            Processed result dictionary.
        """
        import json

        method = result.get('method', 'unknown')
        timestamp = datetime.now().strftime('%Y%m%d')

        if method == 'zip_download':
            # Extract and process ZIP
            extract_dir = self.data_dir / f"cost_reports_{fiscal_year}"
            extract_dir.mkdir(exist_ok=True)

            content = result.get('content', b'')
            extracted_files = []
            total_records = 0

            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for filename in zf.namelist():
                    if filename.endswith('.csv') or filename.endswith('.CSV'):
                        zf.extract(filename, extract_dir)
                        filepath = extract_dir / filename
                        extracted_files.append(str(filepath))

                        try:
                            with open(filepath, 'r') as f:
                                total_records += sum(1 for _ in f) - 1
                        except Exception:
                            pass

            processed_file = self._process_cost_reports(extract_dir, fiscal_year)

            final_result = {
                'status': 'success',
                'extracted_files': extracted_files,
                'processed_file': processed_file,
                'records': total_records,
                'fiscal_year': fiscal_year,
                'extract_dir': str(extract_dir),
                'method': 'catalog_zip',
            }

        elif method == 'csv_download':
            # Save CSV content
            filename = f"cost_reports_{fiscal_year}_{timestamp}.csv"
            filepath = self.data_dir / filename

            with open(filepath, 'wb') as f:
                f.write(result.get('content', b''))

            import pandas as pd
            try:
                df = pd.read_csv(filepath, dtype={'PRVDR_NUM': str}, low_memory=False)
                record_count = len(df)
            except Exception as e:
                logger.warning(f"Could not count records: {e}")
                record_count = None

            final_result = {
                'status': 'success',
                'filepath': str(filepath),
                'records': record_count,
                'fiscal_year': fiscal_year,
                'hash': self.calculate_hash(filepath),
                'method': 'catalog_csv',
            }

        elif method == 'api_paginated':
            # Save JSON data
            data = result.get('data', [])
            filename = f"cost_reports_{fiscal_year}_{timestamp}.json"
            filepath = self.data_dir / filename

            with open(filepath, 'w') as f:
                json.dump(data, f)

            final_result = {
                'status': 'success',
                'filepath': str(filepath),
                'records': len(data),
                'fiscal_year': fiscal_year,
                'hash': self.calculate_hash(filepath),
                'method': 'catalog_api',
            }

        else:
            final_result = {
                'status': 'failed',
                'error': f"Unknown method: {method}",
            }

        self.log_fetch_result(final_result)
        return final_result

    def _fetch_legacy(self, fiscal_year: int) -> dict[str, Any]:
        """
        Legacy fetch using HCRIS download URLs.

        Args:
            fiscal_year: Fiscal year.

        Returns:
            Fetch result dictionary.
        """
        # Try multiple URL patterns
        urls_to_try = [
            f"{self.HCRIS_BASE}/hosp10-{fiscal_year}-HCRIS.zip",
            f"https://downloads.cms.gov/files/hcris/HOSP10-REPORTS-{fiscal_year}.zip",
            f"https://www.cms.gov/files/zip/hospital-{fiscal_year}-cost-report.zip",
        ]

        for url in urls_to_try:
            try:
                logger.info(f"Trying legacy URL: {url}")
                result = self._download_and_extract(url, fiscal_year)
                if result.get('status') == 'success':
                    result['method'] = 'legacy_hcris'
                    return result
            except Exception as e:
                logger.warning(f"URL failed: {url} - {e}")
                continue

        return {
            'status': 'failed',
            'error': 'All legacy URLs failed',
        }

    def _download_and_extract(self, url: str, year: int) -> dict[str, Any]:
        """
        Download and extract cost report ZIP file.

        Args:
            url: URL to download.
            year: Fiscal year.

        Returns:
            Fetch result dictionary.
        """
        import pandas as pd

        logger.info(f"Downloading {url}")
        response = self.session.get(url, stream=True, timeout=600)
        response.raise_for_status()

        # Extract to data directory
        extract_dir = self.data_dir / f"cost_reports_{year}"
        extract_dir.mkdir(exist_ok=True)

        extracted_files = []
        total_records = 0

        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            for filename in zf.namelist():
                if filename.endswith('.csv') or filename.endswith('.CSV'):
                    zf.extract(filename, extract_dir)
                    filepath = extract_dir / filename
                    extracted_files.append(str(filepath))

                    try:
                        pd.read_csv(filepath, nrows=0)
                        with open(filepath, 'r') as f:
                            total_records += sum(1 for _ in f) - 1
                    except Exception:
                        pass

        processed_file = self._process_cost_reports(extract_dir, year)

        return {
            'status': 'success',
            'extracted_files': extracted_files,
            'processed_file': processed_file,
            'records': total_records,
            'fiscal_year': year,
            'extract_dir': str(extract_dir),
        }

    def _process_cost_reports(self, extract_dir, year: int) -> Optional[str]:
        """
        Process raw cost report files into a usable format.

        Args:
            extract_dir: Directory with extracted files.
            year: Fiscal year.

        Returns:
            Path to processed file or None.
        """
        import pandas as pd

        try:
            extract_path = Path(extract_dir)

            # Find the RPT (report) and NMRC (numeric) files
            rpt_files = list(extract_path.glob('*RPT*.csv')) + list(extract_path.glob('*rpt*.csv'))
            nmrc_files = list(extract_path.glob('*NMRC*.csv')) + list(extract_path.glob('*nmrc*.csv'))

            if not rpt_files:
                logger.warning("No RPT file found in cost reports")
                return None

            # Read report file for provider info
            rpt_df = pd.read_csv(rpt_files[0], dtype={'PRVDR_NUM': str})

            if nmrc_files:
                nmrc_df = pd.read_csv(nmrc_files[0], dtype={'PRVDR_NUM': str})
                processed = self._extract_key_metrics(rpt_df, nmrc_df)
            else:
                processed = rpt_df[['PRVDR_NUM', 'PRVDR_CTRL_TYPE_CD', 'FY_BGN_DT', 'FY_END_DT']].copy()

            # Save processed file
            output_file = self.data_dir / f"cost_reports_processed_{year}.csv"
            processed.to_csv(output_file, index=False)

            return str(output_file)

        except Exception as e:
            logger.warning(f"Failed to process cost reports: {e}")
            return None

    def _extract_key_metrics(self, rpt_df, nmrc_df):
        """
        Extract key financial metrics from cost report data.

        Args:
            rpt_df: Report dataframe with provider info.
            nmrc_df: Numeric data with financial values.

        Returns:
            Processed dataframe with key metrics.
        """

        try:
            # Get unique providers from report file
            providers = rpt_df[['PRVDR_NUM', 'FY_BGN_DT', 'FY_END_DT', 'RPT_REC_NUM']].drop_duplicates()

            # Key worksheet/line/column positions for HCRIS 2552-10
            metrics = {
                ('S300001', '00100', '01200'): 'total_beds',
                ('S300001', '01400', '01200'): 'total_discharges',
                ('G300000', '00300', '00100'): 'net_patient_revenue',
                ('G300000', '02500', '00100'): 'total_operating_expenses',
            }

            results = providers.copy()

            for (wksht, line, col), metric_name in metrics.items():
                metric_data = nmrc_df[
                    (nmrc_df['WKSHT_CD'] == wksht) &
                    (nmrc_df['LINE_NUM'] == line) &
                    (nmrc_df['CLMN_NUM'] == col)
                ][['PRVDR_NUM', 'ITM_VAL_NUM']].copy()

                metric_data = metric_data.rename(columns={'ITM_VAL_NUM': metric_name})
                results = results.merge(metric_data, on='PRVDR_NUM', how='left')

            # Calculate derived metrics
            if 'net_patient_revenue' in results.columns and 'total_operating_expenses' in results.columns:
                results['operating_margin'] = (
                    (results['net_patient_revenue'] - results['total_operating_expenses']) /
                    results['net_patient_revenue']
                ).round(4)

            return results

        except Exception as e:
            logger.warning(f"Metric extraction failed: {e}")
            return rpt_df[['PRVDR_NUM', 'FY_BGN_DT', 'FY_END_DT']].drop_duplicates()

    def fetch_all_years(self) -> dict[str, Any]:
        """
        Fetch cost reports for all available years.

        Returns:
            Combined fetch results.
        """
        results = {}
        total_records = 0

        for year in self.AVAILABLE_YEARS:
            logger.info(f"Fetching cost reports for {year}")
            result = self.fetch(fiscal_year=year)
            results[year] = result

            if result.get('status') == 'success':
                total_records += result.get('records', 0)

        return {
            'status': 'success',
            'years': results,
            'total_records': total_records,
        }

    def get_api_endpoints(self) -> dict[str, str]:
        """Return available API endpoints for cost report data."""
        year = max(self.AVAILABLE_YEARS)
        endpoints = {
            'legacy_hcris': f"{self.HCRIS_BASE}/hosp10-{year}-HCRIS.zip",
            'data_cms_api': self.COST_REPORT_API,
        }

        # Add catalog-discovered endpoints
        dataset_info = self.catalog.get_dataset_by_title(self.DATASET_TITLE)
        if not dataset_info:
            dataset_info = self.catalog.get_dataset_by_title(self.DATASET_TITLE_ALT)

        if dataset_info:
            endpoints['catalog_identifier'] = dataset_info.identifier
            endpoints['catalog_modified'] = dataset_info.modified
            zip_url = dataset_info.get_zip_url()
            if zip_url:
                endpoints['catalog_zip'] = zip_url
            csv_url = dataset_info.get_csv_url()
            if csv_url:
                endpoints['catalog_csv'] = csv_url

        return endpoints
