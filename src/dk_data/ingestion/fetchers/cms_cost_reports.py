"""CMS Hospital Cost Reports (HCRIS) Fetcher.

Fetches hospital financial data for financial capacity scoring.
Source: https://www.cms.gov/Research-Statistics-Data-and-Systems/Downloadable-Public-Use-Files/Cost-Reports
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
import zipfile
import io

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSCostReportsFetcher(BaseFetcher):
    """Fetcher for CMS Hospital Cost Reports (HCRIS) data."""

    SOURCE_NAME = "cms_cost_reports"
    BASE_URL = "https://www.cms.gov/Research-Statistics-Data-and-Systems/Downloadable-Public-Use-Files/Cost-Reports"

    # Direct download URLs for HCRIS files
    # CMS provides annual ZIP files with multiple CSVs
    HCRIS_BASE = "https://downloads.cms.gov/files/hcris"

    # Alternative: Hospital Provider Cost Report from data.cms.gov (discovered 2026-01-04)
    # This provides a pre-processed summary dataset
    COST_REPORT_API = "https://data.cms.gov/provider-compliance/cost-report/hospital-provider-cost-report/data"

    # Key report files within the ZIP
    REPORT_FILES = {
        'rpt': 'Report file with provider info and report dates',
        'nmrc': 'Numeric data (costs, revenues, beds)',
        'alpha': 'Alpha data (provider name, address)',
    }

    # Available years
    AVAILABLE_YEARS = [2020, 2021, 2022, 2023]

    def get_latest_url(self) -> str:
        """Get URL for latest cost report data."""
        year = max(self.AVAILABLE_YEARS)
        return f"{self.HCRIS_BASE}/hosp10-{year}-HCRIS.zip"

    def fetch(self, fiscal_year: Optional[int] = None) -> Dict[str, Any]:
        """
        Fetch CMS Hospital Cost Reports.

        Args:
            fiscal_year: Specific fiscal year (defaults to latest)

        Returns:
            Fetch result dictionary
        """
        try:
            year = fiscal_year or max(self.AVAILABLE_YEARS)
            logger.info(f"Fetching CMS Cost Reports for FY{year}")

            # Download ZIP file
            zip_url = f"{self.HCRIS_BASE}/hosp10-{year}-HCRIS.zip"

            try:
                result = self._download_and_extract(zip_url, year)
            except Exception as e:
                # Try alternative URL patterns
                alt_urls = [
                    f"https://downloads.cms.gov/files/hcris/HOSP10-REPORTS-{year}.zip",
                    f"https://www.cms.gov/files/zip/hospital-{year}-cost-report.zip",
                ]

                for alt_url in alt_urls:
                    try:
                        logger.info(f"Trying alternative URL: {alt_url}")
                        result = self._download_and_extract(alt_url, year)
                        break
                    except Exception:
                        continue
                else:
                    raise e

            self.log_fetch_result(result)
            return result

        except Exception as e:
            logger.exception(f"Failed to fetch CMS Cost Reports: {e}")
            result = {
                'status': 'failed',
                'error': str(e),
            }
            self.log_fetch_result(result)
            return result

    def _download_and_extract(self, url: str, year: int) -> Dict[str, Any]:
        """
        Download and extract cost report ZIP file.

        Args:
            url: URL to download
            year: Fiscal year

        Returns:
            Fetch result dictionary
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
                    # Extract file
                    zf.extract(filename, extract_dir)
                    filepath = extract_dir / filename
                    extracted_files.append(str(filepath))

                    # Count records for CSV files
                    try:
                        # Read just the header to check
                        df = pd.read_csv(filepath, nrows=0)
                        # Count lines (faster than full read)
                        with open(filepath, 'r') as f:
                            total_records += sum(1 for _ in f) - 1  # Subtract header
                    except Exception:
                        pass

        # Also create a combined/processed file for key metrics
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
            extract_dir: Directory with extracted files
            year: Fiscal year

        Returns:
            Path to processed file or None
        """
        import pandas as pd
        from pathlib import Path

        try:
            extract_path = Path(extract_dir)

            # Find the RPT (report) file
            rpt_files = list(extract_path.glob('*RPT*.csv')) + list(extract_path.glob('*rpt*.csv'))
            nmrc_files = list(extract_path.glob('*NMRC*.csv')) + list(extract_path.glob('*nmrc*.csv'))

            if not rpt_files:
                logger.warning("No RPT file found in cost reports")
                return None

            # Read report file for provider info
            rpt_df = pd.read_csv(rpt_files[0], dtype={'PRVDR_NUM': str})

            # Extract key fields
            if nmrc_files:
                # NMRC file has worksheet/line/column data
                # Key metrics are in specific worksheet positions
                nmrc_df = pd.read_csv(nmrc_files[0], dtype={'PRVDR_NUM': str})

                # Merge and extract key metrics
                # Worksheet G-3, Lines 3-5 have bed counts
                # Worksheet S-10, Line 200 has operating margin
                # This is complex; create simplified output

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

    def _extract_key_metrics(self, rpt_df, nmrc_df) -> 'pd.DataFrame':
        """
        Extract key financial metrics from cost report data.

        Args:
            rpt_df: Report dataframe with provider info
            nmrc_df: Numeric data with financial values

        Returns:
            Processed dataframe with key metrics
        """
        import pandas as pd

        try:
            # Get unique providers from report file
            providers = rpt_df[['PRVDR_NUM', 'FY_BGN_DT', 'FY_END_DT', 'RPT_REC_NUM']].drop_duplicates()

            # Key worksheet/line/column positions for HCRIS 2552-10
            metrics = {
                # (worksheet, line, column): metric_name
                ('S300001', '00100', '01200'): 'total_beds',
                ('S300001', '01400', '01200'): 'total_discharges',
                ('G300000', '00300', '00100'): 'net_patient_revenue',
                ('G300000', '02500', '00100'): 'total_operating_expenses',
            }

            # Extract each metric
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
            # Return basic provider data
            return rpt_df[['PRVDR_NUM', 'FY_BGN_DT', 'FY_END_DT']].drop_duplicates()

    def fetch_all_years(self) -> Dict[str, Any]:
        """
        Fetch cost reports for all available years.

        Returns:
            Combined fetch results
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
