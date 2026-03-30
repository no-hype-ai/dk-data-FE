"""HRSA Health Professional Shortage Area (HPSA) Fetcher.

Fetches shortage area designations for geographic scoring.
Source: https://data.hrsa.gov/
API: https://data.hrsa.gov/data/api
"""

import logging
from datetime import datetime
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

    def fetch(self, hpsa_types: Optional[List[str]] = None, states: Optional[List[str]] = None, **kwargs) -> Dict[str, Any]:
        """
        Fetch HRSA HPSA designation data.

        The data.hrsa.gov JSON API redirects to HTML and is unreliable.
        We use the bulk CSV download directly:
          https://data.hrsa.gov/DataDownload/DD_Files/BCD_HPSA_FCT_DET_PC.csv

        Args:
            hpsa_types: Ignored (bulk download includes all types).
            states: List of state abbreviations to filter.
            max_records: Maximum records to return (default: all).

        Returns:
            Fetch result dictionary
        """
        max_records: Optional[int] = kwargs.get("max_records")
        try:
            result = self._fetch_bulk_download(states=states, max_records=max_records)
            self.log_fetch_result(result)
            return result

        except Exception as e:
            logger.exception(f"Failed to fetch HRSA data: {e}")
            result = {
                'status': 'failed',
                'records': [],
                'record_count': 0,
                'hash': None,
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

    def _fetch_bulk_download(
        self,
        states: Optional[List[str]] = None,
        max_records: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Download and parse the HRSA bulk HPSA CSV files.

        Primary Care CSV is ~44 MB and contains all HPSA designations.
        Mental Health CSV is included if max_records allows.

        Args:
            states: Optional list of state abbreviations to filter rows.
            max_records: Stop after this many records (default: all).

        Returns:
            Fetch result dictionary with status, records (list), hash.
        """
        import csv as _csv
        import hashlib
        import io

        bulk_urls = [
            f"{self.DOWNLOAD_BASE}/BCD_HPSA_FCT_DET_PC.csv",  # Primary Care (~44 MB)
            f"{self.DOWNLOAD_BASE}/BCD_HPSA_FCT_DET_MH.csv",  # Mental Health
        ]

        all_records: List[Dict[str, Any]] = []

        for url in bulk_urls:
            if max_records is not None and len(all_records) >= max_records:
                break
            try:
                logger.info("Downloading HRSA bulk CSV: %s", url)
                response = self.session.get(url, timeout=300, stream=True)
                response.raise_for_status()

                content = response.content
                text = content.decode("utf-8", errors="replace")
                reader = _csv.DictReader(io.StringIO(text))

                for row in reader:
                    if max_records is not None and len(all_records) >= max_records:
                        break
                    if states:
                        state_val = row.get("StateAbbr", row.get("State", row.get("state", "")))
                        if state_val not in states:
                            continue
                    record = {k: (v.strip() if isinstance(v, str) and v.strip() else None) for k, v in row.items()}
                    all_records.append(record)

                logger.info("Parsed %d records from %s", len(all_records), url)

            except Exception as e:
                logger.warning("Failed to download HRSA bulk file %s: %s", url, e)
                continue

        if all_records:
            content_hash = hashlib.md5(str(len(all_records)).encode()).hexdigest()
            return {
                "status": "success",
                "records": all_records,
                "record_count": len(all_records),
                "hash": content_hash,
            }
        else:
            return {
                "status": "failed",
                "error": "No records fetched from HRSA bulk CSV downloads",
                "records": [],
                "record_count": 0,
                "hash": None,
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
