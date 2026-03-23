"""HRSA Health Professional Shortage Area (HPSA) Fetcher.

Fetches shortage area designations for geographic scoring.
Source: https://data.hrsa.gov/
API: https://data.hrsa.gov/data/api
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import json

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class HRSAFetcher(BaseFetcher):
    """Fetcher for HRSA Health Professional Shortage Area data."""

    SOURCE_NAME = "hrsa_shortage_areas"
    BASE_URL = "https://data.hrsa.gov"

    # HRSA Data API endpoints
    API_BASE = "https://data.hrsa.gov/data/api"
    HPSA_API = "https://data.hrsa.gov/data/api/HPSA"

    # Download endpoints
    DOWNLOAD_BASE = "https://data.hrsa.gov/DataDownload/DD_Files"

    # HPSA types
    HPSA_TYPES = ['Primary Care', 'Dental Health', 'Mental Health']

    def get_latest_url(self) -> str:
        """Get URL for HPSA data."""
        return f"{self.HPSA_API}/designations"

    def fetch(self, hpsa_types: Optional[List[str]] = None, states: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Fetch HRSA HPSA designation data.

        Args:
            hpsa_types: List of HPSA types to fetch (defaults to Primary Care only)
            states: List of state abbreviations to filter

        Returns:
            Fetch result dictionary
        """
        try:
            types = hpsa_types or ['Primary Care']
            logger.info(f"Fetching HRSA HPSA data for types: {types}")

            all_records = []

            for hpsa_type in types:
                records = self._fetch_hpsa_type(hpsa_type, states)
                all_records.extend(records)

            if all_records:
                filename = f"hrsa_hpsa_{datetime.now().strftime('%Y%m%d')}.json"
                filepath = self.data_dir / filename

                with open(filepath, 'w') as f:
                    json.dump(all_records, f, indent=2)

                content_hash = self.calculate_hash(filepath)
                self.save_manifest(
                    last_run_at=datetime.now(timezone.utc).isoformat(),
                    last_run_status="completed",
                    total_records_fetched=len(all_records),
                    last_content_hash=content_hash,
                )
                result = {
                    'status': 'success',
                    'filepath': str(filepath),
                    'records': len(all_records),
                    'hash': content_hash,
                    'hpsa_types': types,
                }
            else:
                # Try bulk download
                result = self._fetch_bulk_download()
                if result.get('status') == 'success':
                    self.save_manifest(
                        last_run_at=datetime.now(timezone.utc).isoformat(),
                        last_run_status="completed",
                        total_records_fetched=result.get('records', 0),
                    )

            self.log_fetch_result(result)
            return result

        except Exception as e:
            logger.exception(f"Failed to fetch HRSA data: {e}")
            self.save_manifest(last_run_status="interrupted")
            result = {
                'status': 'failed',
                'error': str(e),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_hpsa_type(self, hpsa_type: str, states: Optional[List[str]] = None) -> List[Dict]:
        """
        Fetch HPSA data for a specific type.

        Args:
            hpsa_type: Type of HPSA (Primary Care, Mental Health, etc.)
            states: Optional list of states to filter

        Returns:
            List of HPSA records
        """
        records = []

        try:
            # HRSA API endpoint for HPSA designations
            api_url = f"{self.API_BASE}/HPSAs"

            params = {
                'hpsaType': hpsa_type,
                '$top': 1000,
                '$skip': 0,
            }

            while True:
                logger.debug(f"Fetching {hpsa_type} HPSAs, skip={params['$skip']}")
                response = self.session.get(api_url, params=params, timeout=120)

                if response.status_code != 200:
                    logger.warning(f"HPSA API returned {response.status_code}")
                    break

                data = response.json()

                # Handle different response formats
                if isinstance(data, list):
                    batch = data
                elif isinstance(data, dict):
                    batch = data.get('value', data.get('results', data.get('data', [])))
                else:
                    break

                if not batch:
                    break

                # Filter by state if specified
                if states:
                    batch = [r for r in batch if r.get('stateAbbreviation', r.get('state', '')) in states]

                records.extend(batch)

                if len(batch) < params['$top']:
                    break

                params['$skip'] += params['$top']

                # Safety limit
                if params['$skip'] > 100000:
                    logger.warning("Hit safety limit on HPSA pagination")
                    break

        except Exception as e:
            logger.warning(f"Failed to fetch {hpsa_type} HPSAs: {e}")

        logger.info(f"Fetched {len(records)} {hpsa_type} HPSA records")
        return records

    def _fetch_bulk_download(self) -> Dict[str, Any]:
        """
        Fallback: Download bulk HPSA file.

        Returns:
            Fetch result dictionary
        """
        try:
            # HRSA provides bulk downloads
            bulk_urls = [
                f"{self.DOWNLOAD_BASE}/BCD_HPSA_FCT_DET_PC.csv",  # Primary Care
                f"{self.DOWNLOAD_BASE}/BCD_HPSA_FCT_DET_MH.csv",  # Mental Health
            ]

            all_records = 0
            filepaths = []

            for url in bulk_urls:
                try:
                    # Extract filename from URL
                    filename = url.split('/')[-1]
                    dated_filename = f"{filename.replace('.csv', '')}_{datetime.now().strftime('%Y%m%d')}.csv"

                    filepath = self.download_file(url, dated_filename)
                    filepaths.append(str(filepath))

                    import pandas as pd
                    df = pd.read_csv(filepath)
                    all_records += len(df)

                except Exception as e:
                    logger.warning(f"Failed to download {url}: {e}")
                    continue

            if filepaths:
                return {
                    'status': 'success',
                    'filepaths': filepaths,
                    'records': all_records,
                }
            else:
                return {
                    'status': 'failed',
                    'error': 'No bulk downloads succeeded',
                }

        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e),
            }

    def fetch_by_address(self, address: str, city: str, state: str, zip_code: str) -> Dict[str, Any]:
        """
        Look up HPSA status for a specific address.

        Args:
            address: Street address
            city: City name
            state: State abbreviation
            zip_code: ZIP code

        Returns:
            HPSA designation information
        """
        try:
            # HRSA provides a lookup API
            lookup_url = f"{self.API_BASE}/HPSAsByAddress"

            params = {
                'address': address,
                'city': city,
                'state': state,
                'zip': zip_code,
            }

            response = self.session.get(lookup_url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()

            return {
                'status': 'success',
                'address': f"{address}, {city}, {state} {zip_code}",
                'designations': data,
            }

        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e),
            }

    def fetch_mua(self, states: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Fetch Medically Underserved Areas (MUA) data.

        Args:
            states: Optional list of states to filter

        Returns:
            Fetch result dictionary
        """
        try:
            logger.info("Fetching MUA designations")

            api_url = f"{self.API_BASE}/MUAs"
            params = {
                '$top': 1000,
                '$skip': 0,
            }

            all_records = []

            while True:
                response = self.session.get(api_url, params=params, timeout=120)

                if response.status_code != 200:
                    break

                data = response.json()
                batch = data if isinstance(data, list) else data.get('value', [])

                if not batch:
                    break

                if states:
                    batch = [r for r in batch if r.get('stateAbbreviation', '') in states]

                all_records.extend(batch)

                if len(batch) < params['$top']:
                    break

                params['$skip'] += params['$top']

            if all_records:
                filename = f"hrsa_mua_{datetime.now().strftime('%Y%m%d')}.json"
                filepath = self.data_dir / filename

                with open(filepath, 'w') as f:
                    json.dump(all_records, f, indent=2)

                return {
                    'status': 'success',
                    'filepath': str(filepath),
                    'records': len(all_records),
                    'hash': self.calculate_hash(filepath),
                }
            else:
                return {
                    'status': 'failed',
                    'error': 'No MUA records fetched',
                }

        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e),
            }
