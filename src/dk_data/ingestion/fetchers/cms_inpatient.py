"""CMS Medicare Inpatient Hospital Data Fetcher.

Fetches TAVR procedure volumes (DRG 266/267) from CMS.
Source: https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSInpatientFetcher(BaseFetcher):
    """Fetcher for CMS Medicare Inpatient Hospital data."""

    SOURCE_NAME = "cms_medicare_inpatient"
    BASE_URL = "https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals"

    # Dataset UUID from data.cms.gov
    DATASET_ID = "medicare-inpatient-hospitals-by-provider-and-service"

    # API endpoint for direct data access
    API_BASE = "https://data.cms.gov/data-api/v1/dataset"

    # Available fiscal years (update as new data releases)
    AVAILABLE_YEARS = [2021, 2022, 2023]

    def get_latest_url(self) -> str:
        """Get URL for the latest CMS Inpatient data."""
        # CMS data.gov API endpoint
        return f"{self.API_BASE}/{self.DATASET_ID}/data"

    def get_download_url(self, fiscal_year: Optional[int] = None) -> str:
        """
        Get direct download URL for CSV file.

        Args:
            fiscal_year: Specific fiscal year to download

        Returns:
            Download URL for CSV file
        """
        # CMS provides downloadable CSVs for each fiscal year
        # Updated URL format discovered 2026-01-04
        year = fiscal_year or max(self.AVAILABLE_YEARS)
        return f"https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals/medicare-inpatient-hospitals-by-provider-and-service/data?year={year}&_format=csv&headers=display"

    def fetch(self, fiscal_year: Optional[int] = None, filter_tavr: bool = True) -> Dict[str, Any]:
        """
        Fetch CMS Medicare Inpatient data.

        Args:
            fiscal_year: Specific fiscal year (defaults to latest)
            filter_tavr: If True, only fetch TAVR DRG codes (266/267)

        Returns:
            Fetch result dictionary
        """
        try:
            year = fiscal_year or max(self.AVAILABLE_YEARS)
            logger.info(f"Fetching CMS Medicare Inpatient data for FY{year}")

            # Build API query
            # CMS data.gov API supports filtering
            api_url = f"{self.API_BASE}/{self.DATASET_ID}/data.json"

            params = {
                'size': 5000,  # Max page size
                'offset': 0,
            }

            # Filter for TAVR DRG codes if requested
            if filter_tavr:
                # DRG 266: TAVR w/ MCC
                # DRG 267: TAVR w/o MCC
                params['filter[DRG_Cd]'] = '266,267'

            all_records = []
            total_fetched = 0

            # Paginate through results
            while True:
                logger.debug(f"Fetching page at offset {params['offset']}")
                response = self.session.get(api_url, params=params, timeout=120)

                if response.status_code == 404:
                    # Try alternative download method
                    logger.warning("API returned 404, trying CSV download")
                    return self._fetch_csv(year, filter_tavr)

                response.raise_for_status()
                data = response.json()

                if not data:
                    break

                all_records.extend(data)
                total_fetched += len(data)

                if len(data) < params['size']:
                    break

                params['offset'] += params['size']

                # Safety limit
                if params['offset'] > 50000:
                    logger.warning("Hit safety limit on pagination")
                    break

            # Save to file
            if all_records:
                import json
                filename = f"cms_inpatient_fy{year}_{datetime.now().strftime('%Y%m%d')}.json"
                filepath = self.data_dir / filename

                with open(filepath, 'w') as f:
                    json.dump(all_records, f)

                result = {
                    'status': 'success',
                    'filepath': str(filepath),
                    'records': len(all_records),
                    'fiscal_year': year,
                    'hash': self.calculate_hash(filepath),
                }
            else:
                result = {
                    'status': 'success',
                    'records': 0,
                    'fiscal_year': year,
                    'message': 'No records found',
                }

            self.log_fetch_result(result)
            return result

        except Exception as e:
            logger.exception(f"Failed to fetch CMS Inpatient data: {e}")
            result = {
                'status': 'failed',
                'error': str(e),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_csv(self, fiscal_year: int, filter_tavr: bool) -> Dict[str, Any]:
        """
        Fallback: Download full CSV file.

        Args:
            fiscal_year: Fiscal year to download
            filter_tavr: Whether to filter for TAVR codes

        Returns:
            Fetch result dictionary
        """
        import pandas as pd

        try:
            # Direct CSV download URL (updated 2026-01-04)
            csv_url = f"https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals/medicare-inpatient-hospitals-by-provider-and-service/data?year={fiscal_year}&_format=csv&headers=display"

            logger.info(f"Downloading CSV from {csv_url}")
            filename = f"cms_inpatient_fy{fiscal_year}_{datetime.now().strftime('%Y%m%d')}.csv"
            filepath = self.download_file(csv_url, filename)

            # Count records
            df = pd.read_csv(filepath, dtype={'Rndrng_Prvdr_CCN': str, 'DRG_Cd': str})

            if filter_tavr:
                # Filter and save TAVR-only file
                tavr_df = df[df['DRG_Cd'].isin(['266', '267'])]
                tavr_filename = f"cms_inpatient_tavr_fy{fiscal_year}_{datetime.now().strftime('%Y%m%d')}.csv"
                tavr_filepath = self.data_dir / tavr_filename
                tavr_df.to_csv(tavr_filepath, index=False)

                return {
                    'status': 'success',
                    'filepath': str(tavr_filepath),
                    'records': len(tavr_df),
                    'total_records': len(df),
                    'fiscal_year': fiscal_year,
                    'hash': self.calculate_hash(tavr_filepath),
                }
            else:
                return {
                    'status': 'success',
                    'filepath': str(filepath),
                    'records': len(df),
                    'fiscal_year': fiscal_year,
                    'hash': self.calculate_hash(filepath),
                }

        except Exception as e:
            logger.exception(f"CSV download failed: {e}")
            return {
                'status': 'failed',
                'error': str(e),
            }

    def fetch_all_years(self, filter_tavr: bool = True) -> Dict[str, Any]:
        """
        Fetch data for all available fiscal years.

        Returns:
            Combined fetch results
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
