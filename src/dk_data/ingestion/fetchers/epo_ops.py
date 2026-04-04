"""EPO Open Patent Services (OPS) Fetcher.

Feature: 011-datasource-integration
Task: T061-T063 — EPO OPS patent data

Fetches pharmaceutical patent data from the European Patent Office
Open Patent Services API using OAuth2 authentication.

Source: https://ops.epo.org/3.2/rest-services/
Auth: OAuth2 client_credentials via EPO_CONSUMER_KEY / EPO_CONSUMER_SECRET
"""

import hashlib
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

from ..sources.epo_ops import load_epo_ops_data
from ..utils.checkpoint import clear_checkpoint, load_checkpoint, save_checkpoint
from .base import BaseFetcher

logger = logging.getLogger(__name__)

# IPC codes for pharmaceutical patents:
#   A61K: pharmaceutical preparations (drugs, excipients, dosage forms)
#   A61P: therapeutic activity (by disease/mechanism — ensures clinical relevance)
#   C07D: heterocyclic compounds (small-molecule drugs)
#   C07K: peptides (biologics, GLP-1s, monoclonal antibodies)
#   C07H: nucleosides/nucleotides/nucleic acids (RNA therapeutics, mRNA vaccines)
PHARMA_IPC_CODES = ["A61K", "A61P", "C07D", "C07K", "C07H"]

# Maximum records per fetch run — None means unlimited
MAX_RECORDS = None

# OPS throttle: max 10 requests per minute for registered users
OPS_REQUEST_DELAY = 6.5  # seconds between requests


class EPOOPSFetcher(BaseFetcher):
    """Fetcher for EPO Open Patent Services patent data."""

    SOURCE_NAME = "epo_ops"
    BASE_URL = "https://ops.epo.org/3.2/rest-services"
    TOKEN_URL = "https://ops.epo.org/3.2/auth/accesstoken"

    # OPS search endpoint — /biblio returns full exchange-document elements with titles/abstracts/IPC
    SEARCH_ENDPOINT = "/published-data/search/biblio"

    # Results per page (OPS max is 100)
    PAGE_SIZE = 100

    def __init__(self, data_dir: Optional[str] = None):
        """Initialize the EPO OPS fetcher.

        Reads EPO_CONSUMER_KEY and EPO_CONSUMER_SECRET from environment.
        """
        super().__init__(data_dir)

        self.consumer_key: Optional[str] = os.environ.get("EPO_CONSUMER_KEY")
        self.consumer_secret: Optional[str] = os.environ.get("EPO_CONSUMER_SECRET")
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

        # OPS returns XML by default
        self.session.headers.update({
            "Accept": "application/xml",
        })

        if self.consumer_key and self.consumer_secret:
            logger.info("EPO OPS credentials detected")
        else:
            logger.warning(
                "EPO_CONSUMER_KEY or EPO_CONSUMER_SECRET not set; "
                "API calls will fail"
            )

    def get_latest_url(self) -> str:
        """Get the OPS published-data search endpoint."""
        return f"{self.BASE_URL}{self.SEARCH_ENDPOINT}"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch pharmaceutical patent data from EPO OPS.

        Keyword Args:
            search_terms: List of search terms (default: from DB or built-in).
            ipc_codes: IPC code prefixes to filter (default: A61K, A61P, C07D).
            max_records: Maximum records to fetch (default: 5000).
            days_back: Number of days to look back (default: 30).

        Returns:
            Dict with status, records, hash, error.
        """
        search_terms = kwargs.get("search_terms")
        ipc_codes = kwargs.get("ipc_codes", PHARMA_IPC_CODES)
        raw_max = kwargs.get("max_records", MAX_RECORDS)
        max_records = int(raw_max) if raw_max is not None else None
        # days_back=None means no date filter (full backfill) — default for initial load
        days_back = kwargs.get("days_back", None)
        if days_back is not None:
            days_back = int(days_back) if days_back != 0 else None

        try:
            # Load search terms from DB if not provided
            if not search_terms:
                search_terms = self._load_search_terms()

            if not search_terms:
                search_terms = ["pharmaceutical", "drug therapy"]

            logger.info(
                "Fetching EPO OPS patents (terms=%d, ipc=%s, days_back=%s)",
                len(search_terms), ipc_codes, days_back,
            )

            # Resume from checkpoint if available
            cp = load_checkpoint(self.SOURCE_NAME)
            start_term_index = 0
            total_fetched = 0
            if cp:
                start_term_index = cp.get("term_index", 0)
                total_fetched = cp.get("total_fetched", 0)
                logger.info(
                    "EPO OPS: resuming from checkpoint term_index=%d total=%d",
                    start_term_index, total_fetched,
                )

            # Authenticate
            self._ensure_token()

            for term_index, term in enumerate(search_terms):
                if term_index < start_term_index:
                    continue
                if max_records is not None and total_fetched >= max_records:
                    break

                term_count = self._stream_patents(
                    term,
                    term_index=term_index,
                    ipc_codes=ipc_codes,
                    days_back=days_back,
                    max_records=(max_records - total_fetched) if max_records is not None else None,
                )
                total_fetched += term_count

                # Checkpoint after each term
                save_checkpoint(self.SOURCE_NAME, {
                    "term_index": term_index + 1,
                    "total_fetched": total_fetched,
                })

            clear_checkpoint(self.SOURCE_NAME)

            content_hash = hashlib.md5(
                f"epo_ops:{total_fetched}".encode()
            ).hexdigest()

            result = {
                "status": "success",
                "records": [],  # already in DB
                "record_count": total_fetched,
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": total_fetched})
            return result

        except RuntimeError as e:
            # Missing credentials — not a transient failure
            logger.warning("EPO OPS: %s", e)
            result = {
                "status": "source_unavailable",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(e),
            }
            self.log_fetch_result(result)
            return result
        except Exception as e:
            # Distinguish 401/403 (credential expiry) from generic failures
            err_str = str(e)
            if "401" in err_str or "403" in err_str:
                logger.warning(
                    "EPO OPS auth failure (401/403) — credentials may have expired. "
                    "Rotate EPO_CONSUMER_KEY / EPO_CONSUMER_SECRET: %s", e
                )
                result = {
                    "status": "source_unavailable",
                    "records": [],
                    "record_count": 0,
                    "hash": None,
                    "error": f"Auth failure (rotate EPO_CONSUMER_KEY/SECRET): {e}",
                }
            else:
                logger.exception("Failed to fetch EPO OPS data: %s", e)
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
    # Authentication
    # ------------------------------------------------------------------

    def _ensure_token(self) -> None:
        """Obtain or refresh OAuth2 access token."""
        if self._access_token and time.time() < self._token_expires_at:
            return

        if not self.consumer_key or not self.consumer_secret:
            raise RuntimeError("EPO_CONSUMER_KEY and EPO_CONSUMER_SECRET are required")

        logger.debug("Requesting new EPO OPS access token")
        response = self.session.post(
            self.TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self.consumer_key, self.consumer_secret),
            headers={"Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        token_data = response.json()

        self._access_token = token_data["access_token"]
        # Expire 60 seconds early for safety
        expires_in = int(token_data.get("expires_in", 1200))
        self._token_expires_at = time.time() + expires_in - 60

        logger.info("EPO OPS access token obtained (expires_in=%d)", expires_in)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _stream_patents(
        self,
        term: str,
        *,
        term_index: int,
        ipc_codes: List[str],
        days_back: Optional[int] = None,
        max_records: Optional[int] = None,
    ) -> int:
        """Search OPS for patents matching a term, writing each page directly to DB.

        Returns:
            Number of patent records written to DB for this term.
        """
        # Build CQL query — OPS CQL uses bare IPC codes (no quotes)
        ipc_filter = " OR ".join(f'ipc={code}' for code in ipc_codes)
        if days_back:
            date_from = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y%m%d")
            cql = f'txt="{term}" AND ({ipc_filter}) AND pd>={date_from}'
        else:
            cql = f'txt="{term}" AND ({ipc_filter})'

        start = 1
        total = 0

        while max_records is None or total < max_records:
            remaining = (max_records - total) if max_records is not None else self.PAGE_SIZE
            end = start + min(self.PAGE_SIZE, remaining) - 1

            try:
                params = {
                    "q": cql,
                    "Range": f"{start}-{end}",
                }
                headers = {
                    "Authorization": f"Bearer {self._access_token}",
                    "Accept": "application/xml",
                }

                response = self.session.get(
                    self.get_latest_url(),
                    params=params,
                    headers=headers,
                    timeout=60,
                )

                if response.status_code in (400, 404):
                    logger.debug(
                        "OPS %d for term '%s' — no results or invalid range",
                        response.status_code, term,
                    )
                    break

                response.raise_for_status()

                batch = self._parse_search_response(response.content)
                if not batch:
                    break

                # Flush page directly to DB — bounded memory
                load_epo_ops_data(batch)
                total += len(batch)

                if len(batch) < self.PAGE_SIZE:
                    break

                start += self.PAGE_SIZE
                time.sleep(OPS_REQUEST_DELAY)

            except Exception as e:
                logger.warning("OPS search failed for term '%s' at range %d: %s", term, start, e)
                break

        logger.info("EPO OPS term '%s' (index=%d): %d records", term, term_index, total)
        return total

    def _parse_search_response(self, xml_content: bytes) -> List[Dict[str, Any]]:
        """Parse OPS search XML response into record dicts."""
        records: List[Dict[str, Any]] = []

        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            logger.error("Failed to parse OPS XML: %s", e)
            return records

        # OPS uses namespaces
        ns = {
            "ops": "http://ops.epo.org",
            "epo": "http://www.epo.org/exchange",
            "xlink": "http://www.w3.org/1999/xlink",
        }

        for doc in root.findall(".//epo:exchange-document", ns):
            try:
                record = self._parse_document(doc, ns)
                if record:
                    records.append(record)
            except Exception as e:
                logger.warning("Failed to parse OPS document: %s", e)

        return records

    def _parse_document(
        self, doc: ET.Element, ns: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """Parse a single exchange-document element."""
        # Publication ID from attributes
        country = doc.get("country", "")
        doc_number = doc.get("doc-number", "")
        kind = doc.get("kind", "")

        if not doc_number:
            return None

        publication_id = f"{country}{doc_number}{kind}".strip()

        # Title
        title = None
        for title_elem in doc.findall(".//epo:invention-title", ns):
            if title_elem.get("lang", "en") == "en" and title_elem.text:
                title = title_elem.text.strip()
                break
        if title is None:
            title_elem = doc.find(".//epo:invention-title", ns)
            if title_elem is not None and title_elem.text:
                title = title_elem.text.strip()

        # Abstract
        abstract = None
        for abs_elem in doc.findall(".//epo:abstract", ns):
            if abs_elem.get("lang", "en") == "en":
                p_elem = abs_elem.find("epo:p", ns)
                if p_elem is not None and p_elem.text:
                    abstract = p_elem.text.strip()
                    break
        if abstract is None:
            abs_elem = doc.find(".//epo:abstract/epo:p", ns)
            if abs_elem is not None and abs_elem.text:
                abstract = abs_elem.text.strip()

        # Applicants
        applicants = []
        for app in doc.findall(".//epo:applicant/epo:applicant-name/epo:name", ns):
            if app.text:
                applicants.append(app.text.strip())

        # Inventors
        inventors = []
        for inv in doc.findall(".//epo:inventor/epo:inventor-name/epo:name", ns):
            if inv.text:
                inventors.append(inv.text.strip())

        # Filing date
        filing_date = None
        app_ref = doc.find(".//epo:application-reference/epo:document-id/epo:date", ns)
        if app_ref is not None and app_ref.text:
            filing_date = self._parse_date(app_ref.text.strip())

        # Publication date
        publication_date = None
        pub_ref = doc.find(".//epo:publication-reference/epo:document-id/epo:date", ns)
        if pub_ref is not None and pub_ref.text:
            publication_date = self._parse_date(pub_ref.text.strip())

        # IPC codes
        ipc_codes = []
        for ipc in doc.findall(".//epo:classification-ipc/epo:text", ns):
            if ipc.text:
                ipc_codes.append(ipc.text.strip())
        # Also try main-classification
        for ipc in doc.findall(".//epo:classification-ipcr/epo:text", ns):
            if ipc.text:
                ipc_codes.append(ipc.text.strip())

        # CPC codes
        cpc_codes = []
        for cpc in doc.findall(".//epo:classification-cpc/epo:text", ns):
            if cpc.text:
                cpc_codes.append(cpc.text.strip())

        # Family ID
        family_id = doc.get("family-id")

        return {
            "publication_id": publication_id,
            "title": title,
            "abstract": abstract,
            "applicants": applicants if applicants else None,
            "inventors": inventors if inventors else None,
            "filing_date": filing_date,
            "publication_date": publication_date,
            "ipc_codes": ipc_codes if ipc_codes else None,
            "cpc_codes": cpc_codes if cpc_codes else None,
            "family_id": family_id,
        }

    @staticmethod
    def _parse_date(date_str: str) -> Optional[str]:
        """Parse EPO date format (YYYYMMDD) to ISO date string."""
        if not date_str or len(date_str) < 8:
            return None
        try:
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        except (IndexError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Search terms from database
    # ------------------------------------------------------------------

    def _load_search_terms(self) -> List[str]:
        """Load active search terms from meta.ci_search_terms."""
        try:
            from ..utils.database import get_connection

            terms: List[str] = []
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT term_value
                        FROM meta.ci_search_terms
                        WHERE term_type IN ('drug_name', 'therapeutic_area')
                          AND is_active = TRUE
                        ORDER BY term_value
                        """
                    )
                    for row in cur.fetchall():
                        terms.append(row[0])

            logger.info("Loaded %d search terms from meta.ci_search_terms", len(terms))
            return terms

        except Exception as e:
            logger.warning("Could not load search terms from DB: %s", e)
            return []
