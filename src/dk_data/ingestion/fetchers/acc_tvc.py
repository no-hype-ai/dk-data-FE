"""ACC Transcatheter Valve Certification (TVC) Fetcher.

Fetches certified TAVR site list from ACC/CardioSmart.
Source: https://www.cardiosmart.org/find-your-heart-a-home/Hospitals
Map: https://cvquality.acc.org/accreditation/map
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
import json

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class ACCTVCFetcher(BaseFetcher):
    """Fetcher for ACC Transcatheter Valve Certification data."""

    SOURCE_NAME = "acc_tvc"
    BASE_URL = "https://cvquality.acc.org"

    # Known endpoints
    CARDIOSMART_URL = "https://www.cardiosmart.org/find-your-heart-a-home/Hospitals"
    MAP_API_URL = "https://cvquality.acc.org/accreditation/map"

    # ACC accreditation API (may require scraping the map)
    ACCREDITATION_API = "https://cvquality.acc.org/api/accreditation/search"

    def get_latest_url(self) -> str:
        """Get URL for TVC certification data."""
        return self.CARDIOSMART_URL

    def fetch(self, certification_type: Optional[str] = "TVC") -> Dict[str, Any]:
        """
        Fetch ACC TVC certification data.

        Args:
            certification_type: Type of certification to fetch (TVC, Chest Pain, etc.)

        Returns:
            Fetch result dictionary
        """
        try:
            logger.info("Fetching ACC TVC certification data")

            # Try the accreditation map API
            records = self._fetch_from_map_api(certification_type)

            if records:
                filename = f"acc_tvc_{datetime.now().strftime('%Y%m%d')}.json"
                filepath = self.data_dir / filename

                with open(filepath, 'w') as f:
                    json.dump(records, f, indent=2)

                result = {
                    'status': 'success',
                    'filepath': str(filepath),
                    'records': len(records),
                    'hash': self.calculate_hash(filepath),
                }
            else:
                # Fallback to CSV if available
                result = self._fetch_csv()

            self.log_fetch_result(result)
            return result

        except Exception as e:
            logger.exception(f"Failed to fetch ACC TVC data: {e}")
            result = {
                'status': 'failed',
                'error': str(e),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_from_map_api(self, certification_type: str) -> list:
        """
        Attempt to fetch from the accreditation map API.

        Args:
            certification_type: Type of certification

        Returns:
            List of certification records
        """
        try:
            # The ACC map uses a specific API endpoint
            # Try common API patterns
            api_patterns = [
                f"{self.BASE_URL}/api/accreditation/facilities",
                f"{self.BASE_URL}/api/accreditation/search",
                f"{self.BASE_URL}/accreditation/api/facilities",
            ]

            for api_url in api_patterns:
                try:
                    logger.debug(f"Trying API: {api_url}")
                    params = {
                        'type': certification_type,
                        'pageSize': 1000,
                    }
                    response = self.session.get(api_url, params=params, timeout=60)

                    if response.status_code == 200:
                        data = response.json()
                        if isinstance(data, list):
                            return data
                        elif isinstance(data, dict) and 'results' in data:
                            return data['results']
                        elif isinstance(data, dict) and 'data' in data:
                            return data['data']
                except Exception as e:
                    logger.debug(f"API {api_url} failed: {e}")
                    continue

            logger.warning("No working API found, falling back to web scraping")
            return self._scrape_map_page()

        except Exception as e:
            logger.warning(f"Map API fetch failed: {e}")
            return []

    def _scrape_map_page(self) -> list:
        """
        Scrape the accreditation map page for facility data.

        Returns:
            List of certification records
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.warning("BeautifulSoup not installed, cannot scrape map page")
            return []

        try:
            logger.info("Scraping ACC accreditation map page")
            response = self.session.get(self.MAP_API_URL, timeout=60)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Look for embedded JSON data
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string and 'facilities' in script.string.lower():
                    # Try to extract JSON data
                    import re
                    json_match = re.search(r'facilities\s*[=:]\s*(\[.*?\])', script.string, re.DOTALL)
                    if json_match:
                        try:
                            return json.loads(json_match.group(1))
                        except json.JSONDecodeError:
                            continue

            # Look for facility markers in the HTML
            facilities = []
            markers = soup.find_all(attrs={'data-facility': True})
            for marker in markers:
                try:
                    facility_data = json.loads(marker.get('data-facility', '{}'))
                    facilities.append(facility_data)
                except:
                    continue

            return facilities

        except Exception as e:
            logger.warning(f"Map scraping failed: {e}")
            return []

    def _fetch_csv(self) -> Dict[str, Any]:
        """
        Try to fetch CSV from CardioSmart.

        Returns:
            Fetch result dictionary
        """
        try:
            # CardioSmart may have a downloadable CSV
            csv_urls = [
                "https://www.cardiosmart.org/api/hospitals/export",
                "https://www.cardiosmart.org/find-your-heart-a-home/Hospitals/export",
            ]

            for url in csv_urls:
                try:
                    response = self.session.get(url, timeout=60)
                    if response.status_code == 200 and 'csv' in response.headers.get('content-type', ''):
                        filename = f"acc_tvc_{datetime.now().strftime('%Y%m%d')}.csv"
                        filepath = self.data_dir / filename

                        with open(filepath, 'wb') as f:
                            f.write(response.content)

                        import pandas as pd
                        df = pd.read_csv(filepath)

                        return {
                            'status': 'success',
                            'filepath': str(filepath),
                            'records': len(df),
                            'hash': self.calculate_hash(filepath),
                        }
                except Exception as e:
                    logger.debug(f"CSV URL {url} failed: {e}")
                    continue

            return {
                'status': 'failed',
                'error': 'No CSV download available',
                'message': 'Manual download may be required from CardioSmart website',
            }

        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e),
            }

    def load_manual_csv(self, filepath: str) -> Dict[str, Any]:
        """
        Load a manually downloaded CSV file.

        Args:
            filepath: Path to manually downloaded CSV

        Returns:
            Load result dictionary
        """
        import pandas as pd
        from pathlib import Path

        try:
            source_path = Path(filepath)
            if not source_path.exists():
                return {'status': 'failed', 'error': f'File not found: {filepath}'}

            # Copy to data directory
            dest_filename = f"acc_tvc_{datetime.now().strftime('%Y%m%d')}.csv"
            dest_path = self.data_dir / dest_filename

            import shutil
            shutil.copy(source_path, dest_path)

            df = pd.read_csv(dest_path)

            return {
                'status': 'success',
                'filepath': str(dest_path),
                'records': len(df),
                'hash': self.calculate_hash(dest_path),
                'source': 'manual_upload',
            }

        except Exception as e:
            return {'status': 'failed', 'error': str(e)}
