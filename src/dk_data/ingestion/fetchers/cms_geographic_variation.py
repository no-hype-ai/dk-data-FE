"""CMS Geographic Variation Public Use File (GV PUF) Fetcher.

Feature: 019-cms-puf-platform-reconciliation

Fetches CMS Medicare Geographic Variation data which provides state- and
county-level Medicare utilization, spending, and readmission metrics.

Source:
  https://www.cms.gov/Research-Statistics-Data-and-Systems/Statistics-Trends-and-Reports/Medicare-Geographic-Variation
"""

import logging
from datetime import datetime
from typing import Any, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSGeographicVariationFetcher(BaseFetcher):
    """Fetcher for CMS Medicare Geographic Variation PUF data."""

    SOURCE_NAME = "cms_geographic_variation"

    # Available reference years (add new years as CMS publishes them)
    AVAILABLE_YEARS = [2019, 2020, 2021, 2022]

    # Known direct download URL patterns for the GV PUF ZIP files.
    # CMS publishes one ZIP per year containing state and county CSV files.
    # URL pattern: https://www.cms.gov/files/zip/geographic-variation-{year}.zip
    # Fallback: data.cms.gov API dataset identifier
    GV_PUF_DATASET_ID = "gv-puf"
    DATA_CMS_API = "https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-geographic-variation"

    # Known working ZIP URLs (updated 2026-03-01)
    KNOWN_ZIP_URLS = {
        2022: "https://www.cms.gov/files/zip/2022-geographic-variation-public-use-file.zip",
        2021: "https://www.cms.gov/files/zip/2021-geographic-variation-public-use-file.zip",
        2020: "https://www.cms.gov/files/zip/2020-geographic-variation-public-use-file.zip",
        2019: "https://www.cms.gov/files/zip/2019-geographic-variation-public-use-file.zip",
    }

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)

    def fetch(self, year: Optional[int] = None) -> dict[str, Any]:
        """
        Fetch CMS Geographic Variation PUF for the specified year.

        Args:
            year: Reference year (defaults to latest available).

        Returns:
            Fetch result dictionary with status, filepath, records, hash.
        """
        target_year = year or max(self.AVAILABLE_YEARS)
        logger.info(f"Fetching CMS Geographic Variation PUF for {target_year}")

        try:
            result = self._fetch_zip(target_year)
            if result.get('status') == 'success':
                return result

            logger.warning(f"ZIP fetch failed for {target_year}, trying CSV fallback")
            return self._fetch_csv_fallback(target_year)

        except Exception as e:
            logger.exception(f"Failed to fetch CMS Geographic Variation: {e}")
            result = {'status': 'failed', 'error': str(e), 'year': target_year}
            self.log_fetch_result(result)
            return result

    def _fetch_zip(self, year: int) -> dict[str, Any]:
        """Download and extract the GV PUF ZIP for the given year."""
        import io
        import zipfile
        import pandas as pd

        zip_url = self.KNOWN_ZIP_URLS.get(year)
        if not zip_url:
            return {'status': 'failed', 'error': f'No known URL for year {year}'}

        logger.info(f"Downloading GV PUF ZIP: {zip_url}")
        response = self.session.get(zip_url, timeout=300, stream=True)
        response.raise_for_status()

        content_type = response.headers.get('content-type', '')
        if 'html' in content_type.lower():
            return {'status': 'failed', 'error': f'Got HTML instead of ZIP from {zip_url}'}

        content = response.content
        extract_dir = self.data_dir / f"geographic_variation_{year}"
        extract_dir.mkdir(exist_ok=True)

        extracted_files = []
        total_records = 0

        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for name in zf.namelist():
                if name.lower().endswith('.csv'):
                    zf.extract(name, extract_dir)
                    filepath = extract_dir / name
                    extracted_files.append(str(filepath))
                    try:
                        df = pd.read_csv(filepath, dtype={'Bene_Geo_Cd': str}, low_memory=False)
                        total_records += len(df)
                    except Exception:
                        pass

        if not extracted_files:
            return {'status': 'failed', 'error': 'No CSV files found in ZIP'}

        result = {
            'status': 'success',
            'extracted_files': extracted_files,
            'records': total_records,
            'year': year,
            'extract_dir': str(extract_dir),
            'method': 'zip_download',
        }
        self.log_fetch_result(result)
        return result

    def _fetch_csv_fallback(self, year: int) -> dict[str, Any]:
        """
        Fallback: try to download individual CSV files from CMS if the ZIP fails.
        Returns a failed result if nothing works.
        """
        logger.warning(f"No CSV fallback configured for GV PUF year {year}")
        result = {
            'status': 'failed',
            'error': f'All download methods failed for year {year}',
            'year': year,
        }
        self.log_fetch_result(result)
        return result

    def fetch_all_years(self) -> dict[str, Any]:
        """Fetch GV PUF for all available years."""
        results = {}
        total_records = 0

        for year in self.AVAILABLE_YEARS:
            result = self.fetch(year=year)
            results[year] = result
            if result.get('status') == 'success':
                total_records += result.get('records', 0)

        return {
            'status': 'success',
            'years': results,
            'total_records': total_records,
        }
