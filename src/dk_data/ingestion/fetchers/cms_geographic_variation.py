"""CMS Geographic Variation Public Use File (GV PUF) Fetcher.

Feature: 019-cms-puf-platform-reconciliation

Fetches CMS Medicare Geographic Variation data which provides state- and
county-level Medicare utilization, spending, and readmission metrics.

Source:
  https://www.cms.gov/Research-Statistics-Data-and-Systems/Statistics-Trends-and-Reports/Medicare-Geographic-Variation
"""

import logging
from typing import Any, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSGeographicVariationFetcher(BaseFetcher):
    """Fetcher for CMS Medicare Geographic Variation PUF data."""

    SOURCE_NAME = "cms_geographic_variation"

    # Available reference years (newest first; fetcher tries them in this order)
    AVAILABLE_YEARS = [2022, 2021, 2020, 2019]

    # Known direct download URL patterns for the GV PUF ZIP files.
    # CMS publishes one ZIP per year containing state and county CSV files.
    # Multiple URL patterns per year — CMS periodically restructures its file paths.
    GV_PUF_DATASET_ID = "gv-puf"
    DATA_CMS_API = "https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-geographic-variation"

    # Candidate ZIP URLs per year (try in order; stop at first 200).
    KNOWN_ZIP_URLS: dict[int, list[str]] = {
        2022: [
            "https://www.cms.gov/files/zip/2022-geographic-variation-public-use-file.zip",
            "https://www.cms.gov/files/zip/geographic-variation-2022.zip",
            "https://data.cms.gov/sites/default/files/2023-09/2022-geographic-variation-public-use-file.zip",
        ],
        2021: [
            "https://www.cms.gov/files/zip/2021-geographic-variation-public-use-file.zip",
            "https://www.cms.gov/files/zip/geographic-variation-2021.zip",
            "https://data.cms.gov/sites/default/files/2022-09/2021-geographic-variation-public-use-file.zip",
        ],
        2020: [
            "https://www.cms.gov/files/zip/2020-geographic-variation-public-use-file.zip",
            "https://www.cms.gov/files/zip/geographic-variation-2020.zip",
        ],
        2019: [
            "https://www.cms.gov/files/zip/2019-geographic-variation-public-use-file.zip",
            "https://www.cms.gov/files/zip/geographic-variation-2019.zip",
        ],
    }

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)

    def get_latest_url(self) -> str:
        """Return the first candidate ZIP URL for the most recent available year."""
        latest_year = self.AVAILABLE_YEARS[0]
        return self.KNOWN_ZIP_URLS[latest_year][0]

    def fetch(self, year: Optional[int] = None, **kwargs) -> dict[str, Any]:
        """
        Fetch CMS Geographic Variation PUF for the specified year (or the most
        recent year that has a reachable ZIP).

        Args:
            year: Reference year. If None, tries each year in AVAILABLE_YEARS order.

        Returns:
            Fetch result dictionary with status, filepath, records, hash.
        """
        years_to_try = [year] if year else self.AVAILABLE_YEARS

        last_error: str = "No years attempted"
        for target_year in years_to_try:
            logger.info(f"Fetching CMS Geographic Variation PUF for {target_year}")
            try:
                result = self._fetch_zip(target_year)
                if result.get('status') == 'success':
                    return result
                last_error = result.get('error', f'ZIP fetch failed for {target_year}')
                logger.warning(f"ZIP fetch failed for {target_year}: {last_error}")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Exception fetching {target_year}: {e}")

        result = {'status': 'failed', 'error': last_error, 'year': years_to_try[-1] if years_to_try else None}
        self.log_fetch_result(result)
        return result

    def _fetch_zip(self, year: int) -> dict[str, Any]:
        """Download and extract the GV PUF ZIP for the given year.

        Tries each candidate URL in KNOWN_ZIP_URLS[year] and returns on first success.
        """
        import io
        import zipfile
        import pandas as pd

        candidate_urls = self.KNOWN_ZIP_URLS.get(year)
        if not candidate_urls:
            return {'status': 'failed', 'error': f'No known URL for year {year}'}

        last_error: str = "No URLs tried"
        for zip_url in candidate_urls:
            logger.info(f"Trying GV PUF ZIP: {zip_url}")
            try:
                response = self.session.get(zip_url, timeout=300, stream=True)
                if response.status_code == 404:
                    logger.debug(f"404 for {zip_url}, trying next")
                    last_error = f"404 Not Found: {zip_url}"
                    continue
                response.raise_for_status()

                content_type = response.headers.get('content-type', '')
                if 'html' in content_type.lower():
                    last_error = f'Got HTML instead of ZIP from {zip_url}'
                    continue

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
                    last_error = 'No CSV files found in ZIP'
                    continue

                result = {
                    'status': 'success',
                    'extracted_files': extracted_files,
                    'records': total_records,
                    'year': year,
                    'extract_dir': str(extract_dir),
                    'method': 'zip_download',
                    'url': zip_url,
                }
                self.log_fetch_result(result)
                return result

            except Exception as exc:
                last_error = str(exc)
                logger.debug(f"Error fetching {zip_url}: {exc}")

        return {'status': 'failed', 'error': last_error, 'year': year}

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
