"""SEC EDGAR Filings Fetcher.

Feature: 011-datasource-integration
Task: T070-T072 — SEC EDGAR pharmaceutical filings

Fetches pharmaceutical company SEC filings (10-K, 10-Q, 8-K) from
the EDGAR full-text search API. Filters by SIC codes 2830-2836
(pharmaceutical preparations).

Source: https://efts.sec.gov/LATEST/search-index
Rate limit: 10 requests per second (SEC fair-access policy)
"""

import hashlib
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Pharma SIC codes: 2830-2836 (pharmaceutical preparations)
PHARMA_SIC_CODES = ["2830", "2833", "2834", "2835", "2836"]

# Filing types of interest
FILING_TYPES = ["10-K", "10-Q", "8-K"]

# Max records per fetch run
MAX_RECORDS = 5000

# SEC rate limit: 10 requests per second
SEC_REQUEST_DELAY = 0.12  # ~8 req/s to stay under 10/s limit

# Default User-Agent for SEC
DEFAULT_SEC_USER_AGENT = "dk-data-platform admin@example.com"


class SECEdgarFetcher(BaseFetcher):
    """Fetcher for SEC EDGAR pharmaceutical filings."""

    SOURCE_NAME = "sec_edgar"
    BASE_URL = "https://efts.sec.gov/LATEST"

    # EDGAR full-text search API
    SEARCH_API = "https://efts.sec.gov/LATEST/search-index"

    # EDGAR company search
    COMPANY_SEARCH_API = "https://www.sec.gov/cgi-bin/browse-edgar"

    # EDGAR submissions API (structured JSON)
    SUBMISSIONS_API = "https://data.sec.gov/submissions"

    # Page size
    PAGE_SIZE = 100

    def __init__(self, data_dir: Optional[str] = None):
        """Initialize the SEC EDGAR fetcher.

        Sets the required User-Agent header per SEC policy.
        """
        super().__init__(data_dir)

        self.user_agent = os.environ.get(
            "SEC_USER_AGENT", DEFAULT_SEC_USER_AGENT
        )

        # SEC requires specific User-Agent header
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
        })

        logger.info("SEC EDGAR fetcher initialized (User-Agent: %s)", self.user_agent)

    def get_latest_url(self) -> str:
        """Get the EDGAR full-text search API URL."""
        return self.SEARCH_API

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch pharmaceutical SEC filings.

        Keyword Args:
            filing_types: List of filing types (default: 10-K, 10-Q, 8-K).
            sic_codes: SIC codes for pharma companies (default: 2830-2836).
            max_records: Maximum records to fetch (default: 5000).
            days_back: Number of days to look back (default: 7).

        Returns:
            Dict with status, records, hash, error.
        """
        filing_types = kwargs.get("filing_types", FILING_TYPES)
        sic_codes = kwargs.get("sic_codes", PHARMA_SIC_CODES)
        max_records = kwargs.get("max_records", MAX_RECORDS)
        days_back = kwargs.get("days_back", 7)

        try:
            logger.info(
                "Fetching SEC EDGAR filings (types=%s, sic=%s, days_back=%d)",
                filing_types, sic_codes, days_back,
            )

            all_records: List[Dict[str, Any]] = []
            seen_ids: set = set()

            for filing_type in filing_types:
                if len(all_records) >= max_records:
                    break

                records = self._search_filings(
                    filing_type,
                    sic_codes=sic_codes,
                    days_back=days_back,
                    max_records=max_records - len(all_records),
                )

                for rec in records:
                    acc_num = rec.get("accession_number")
                    if acc_num and acc_num not in seen_ids:
                        seen_ids.add(acc_num)
                        all_records.append(rec)

            content_hash = hashlib.md5(
                str(sorted(seen_ids)).encode()
            ).hexdigest()

            result = {
                "status": "success",
                "records": all_records,
                "record_count": len(all_records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(all_records)})
            return result

        except Exception as e:
            logger.exception("Failed to fetch SEC EDGAR data: %s", e)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(e),
            }
            self.log_fetch_result(result)
            return result

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _search_filings(
        self,
        filing_type: str,
        *,
        sic_codes: List[str],
        days_back: int = 7,
        max_records: int = 5000,
    ) -> List[Dict[str, Any]]:
        """Search EDGAR for filings of a specific type."""
        records: List[Dict[str, Any]] = []
        date_from = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        date_to = datetime.utcnow().strftime("%Y-%m-%d")

        start = 0

        while len(records) < max_records:
            try:
                params = {
                    "forms": filing_type,
                    "dateRange": "custom",
                    "startdt": date_from,
                    "enddt": date_to,
                    "from": start,
                    "size": self.PAGE_SIZE,
                }

                data = self.fetch_json(
                    f"{self.BASE_URL}/search-index", params=params
                )

                hits = self._extract_hits(data)
                if not hits:
                    break

                for hit in hits:
                    record = self._normalize_filing(hit, filing_type)
                    if record and self._is_pharma_company(record, sic_codes):
                        records.append(record)

                if len(hits) < self.PAGE_SIZE:
                    break

                start += self.PAGE_SIZE
                time.sleep(SEC_REQUEST_DELAY)

            except Exception as e:
                logger.warning(
                    "EDGAR search failed for %s at offset %d: %s",
                    filing_type, start, e,
                )
                break

        logger.info("Found %d %s filings from EDGAR", len(records), filing_type)
        return records

    @staticmethod
    def _extract_hits(data: Any) -> List[Dict]:
        """Extract search hits from EDGAR API response."""
        if isinstance(data, dict):
            hits = data.get("hits", {})
            if isinstance(hits, dict):
                return hits.get("hits", [])
            if isinstance(hits, list):
                return hits

            for key in ("results", "filings", "data"):
                if key in data and isinstance(data[key], list):
                    return data[key]

        if isinstance(data, list):
            return data

        return []

    def _normalize_filing(
        self, hit: Dict[str, Any], filing_type: str
    ) -> Optional[Dict[str, Any]]:
        """Normalize an EDGAR search hit into the raw schema."""
        # Handle nested _source structure from Elasticsearch
        source = hit.get("_source", hit)

        accession_number = (
            source.get("accession_number")
            or source.get("accession_no")
            or source.get("adsh")
            or hit.get("_id")
        )
        if not accession_number:
            return None

        accession_number = str(accession_number).strip()

        # Company info
        company_name = (
            source.get("company_name")
            or source.get("entity_name")
            or source.get("display_names", [None])[0]
            if isinstance(source.get("display_names"), list)
            else source.get("company_name")
        )

        cik = source.get("cik") or source.get("entity_id")
        if cik:
            cik = str(cik).strip()

        # Filing date
        filing_date = (
            source.get("filing_date")
            or source.get("file_date")
            or source.get("date_filed")
        )
        if filing_date:
            filing_date = str(filing_date)[:10]

        # Document URL
        document_url = source.get("file_url") or source.get("document_url")
        if not document_url and accession_number and cik:
            # Construct URL from accession number
            acc_clean = accession_number.replace("-", "")
            document_url = (
                f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/"
            )

        # Description
        description = (
            source.get("file_description")
            or source.get("description")
            or source.get("form_name")
        )

        # SIC code (for pharma filtering)
        sic = source.get("sic") or source.get("assigned_sic")

        return {
            "accession_number": accession_number,
            "company_name": company_name,
            "cik": cik,
            "filing_type": filing_type,
            "filing_date": filing_date,
            "document_url": document_url,
            "description": description,
            "_sic": str(sic) if sic else None,
        }

    @staticmethod
    def _is_pharma_company(
        record: Dict[str, Any], sic_codes: List[str]
    ) -> bool:
        """Check if a filing is from a pharmaceutical company by SIC code.

        If no SIC code is available, include the record (we cannot filter).
        """
        sic = record.pop("_sic", None)
        if sic is None:
            return True
        return sic in sic_codes
