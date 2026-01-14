"""CMS Hospital General Information Fetcher.

Fetches hospital demographics, ownership, and quality ratings.
Source: https://data.cms.gov/provider-data/topics/hospitals
"""

import logging
from datetime import datetime
from typing import Dict, Any

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSHospitalInfoFetcher(BaseFetcher):
    """Fetcher for CMS Hospital General Information data."""

    SOURCE_NAME = "cms_hospital_info"
    BASE_URL = "https://data.cms.gov/provider-data"

    # Dataset identifiers
    HOSPITAL_INFO_DATASET = "xubh-q36u"

    # Direct download URLs (from data.cms.gov)
    DOWNLOAD_URLS = {
        'hospital_info': 'https://data.cms.gov/provider-data/sites/default/files/resources/092256becd267d9eeccf73bf7d16c46b_1704412525/Hospital_General_Information.csv',
    }

    def get_latest_url(self) -> str:
        """Get URL for the latest hospital info data."""
        return f"https://data.cms.gov/provider-data/api/1/datastore/query/{self.HOSPITAL_INFO_DATASET}/0"

    def fetch(self) -> Dict[str, Any]:
        """
        Fetch CMS Hospital General Information.

        Returns:
            Fetch result dictionary
        """
        try:
            logger.info("Fetching CMS Hospital General Information")

            # Try API first
            api_url = self.get_latest_url()
            params = {
                'limit': 10000,
                'offset': 0,
            }

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

                    # Safety limit
                    if params['offset'] > 100000:
                        logger.warning("Hit safety limit")
                        break

            except Exception as api_error:
                logger.warning(f"API fetch failed: {api_error}, trying CSV download")
                return self._fetch_csv()

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
                }
            else:
                result = self._fetch_csv()

            self.log_fetch_result(result)
            return result

        except Exception as e:
            logger.exception(f"Failed to fetch CMS Hospital Info: {e}")
            result = {
                'status': 'failed',
                'error': str(e),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_csv(self) -> Dict[str, Any]:
        """
        Download CSV directly from CMS.

        Returns:
            Fetch result dictionary
        """
        import pandas as pd

        try:
            # Try to find latest CSV URL from the dataset page
            # Fallback to known working URL pattern
            csv_url = "https://data.cms.gov/provider-data/sites/default/files/resources/092256becd267d9eeccf73bf7d16c46b_1704412525/Hospital_General_Information.csv"

            logger.info(f"Downloading Hospital Info CSV from {csv_url}")
            filename = f"cms_hospital_info_{datetime.now().strftime('%Y%m%d')}.csv"

            try:
                filepath = self.download_file(csv_url, filename)
            except Exception:
                # Try alternative URL pattern
                alt_url = "https://data.cms.gov/provider-data/dataset/xubh-q36u/data.csv"
                logger.info(f"Trying alternative URL: {alt_url}")
                filepath = self.download_file(alt_url, filename)

            # Count records
            df = pd.read_csv(filepath, dtype={'Facility ID': str, 'ZIP Code': str})

            return {
                'status': 'success',
                'filepath': str(filepath),
                'records': len(df),
                'hash': self.calculate_hash(filepath),
            }

        except Exception as e:
            logger.exception(f"CSV download failed: {e}")
            return {
                'status': 'failed',
                'error': str(e),
            }

    def get_api_endpoints(self) -> Dict[str, str]:
        """Return available API endpoints for hospital data."""
        # Updated URLs discovered 2026-01-04
        return {
            'hospital_info': f"https://data.cms.gov/provider-data/api/1/datastore/query/{self.HOSPITAL_INFO_DATASET}/0",
            'download_csv': "https://data.cms.gov/provider-data/dataset/xubh-q36u/data.csv",
            # Paginated API: use limit/offset params
            'api_paginated': f"https://data.cms.gov/provider-data/api/1/datastore/query/{self.HOSPITAL_INFO_DATASET}/0?limit=500&offset=0",
        }
