"""SEC EDGAR Filings Fetcher.

Feature: 011-datasource-integration
Task: T070-T072 — SEC EDGAR pharmaceutical filings

Fetches pharmaceutical company SEC filings (10-K, 10-Q, 8-K) from
the EDGAR full-text search API (EFTS). Uses the `forms` parameter
for form-type filtering and `q` for full-text queries.

Source: https://efts.sec.gov/LATEST/search-index
Rate limit: 10 requests per second (SEC fair-access policy)
"""

import hashlib
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Pharma SIC codes: 2830-2836 (pharmaceutical preparations)
PHARMA_SIC_CODES = ["2830", "2833", "2834", "2835", "2836"]

# Filing types of interest
FILING_TYPES = ["10-K", "10-Q", "8-K", "20-F"]

# Max records per fetch run
MAX_RECORDS = 5000

# SEC rate limit: 10 requests per second
SEC_REQUEST_DELAY = 0.12  # ~8 req/s to stay under 10/s limit

# Base URL for SEC Archives (used for FilingSummary.xml and index.json lookups)
SEC_ARCHIVES_URL = "https://www.sec.gov"

# Default User-Agent for SEC
DEFAULT_SEC_USER_AGENT = "dk-data-platform admin@example.com"


class SECEdgarFetcher(BaseFetcher):
    """Fetcher for SEC EDGAR pharmaceutical filings."""

    SOURCE_NAME = "sec_edgar"
    BASE_URL = "https://efts.sec.gov/LATEST"

    # EDGAR full-text search API
    SEARCH_API = "https://efts.sec.gov/LATEST/search-index"

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
        search_terms = kwargs.get("search_terms")

        # When a specific company name is provided, skip SIC filtering
        # (the company name itself is the filter — we trust the caller)
        skip_sic_filter = bool(search_terms)

        # Load search terms from DB if not provided; fall back to defaults
        if not search_terms:
            search_terms = self._load_search_terms()
        if not search_terms:
            search_terms = ["pharmaceutical", "drug", "FDA approval", "clinical trial"]
            logger.info(
                "No search terms from DB; using %d default pharma terms for SEC EDGAR",
                len(search_terms),
            )

        try:
            logger.info(
                "Fetching SEC EDGAR filings (types=%s, sic=%s, days_back=%d, terms=%d)",
                filing_types, sic_codes, days_back, len(search_terms),
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
                    search_terms=search_terms,
                    skip_sic_filter=skip_sic_filter,
                )

                for rec in records:
                    acc_num = rec.get("accession_number")
                    if acc_num and acc_num not in seen_ids:
                        seen_ids.add(acc_num)
                        all_records.append(rec)

            content_hash = hashlib.md5(
                str(sorted(seen_ids)).encode()
            ).hexdigest()

            self.save_manifest(
                last_run_at=datetime.now(timezone.utc).isoformat(),
                last_run_status="completed",
                total_records_fetched=len(all_records),
                last_content_hash=content_hash,
            )

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
            self.save_manifest(last_run_status="interrupted")
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

    def _load_search_terms(self) -> List[str]:
        """Load search terms from meta.ops_ci_search_terms."""
        try:
            from ..utils.database import get_connection

            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT term_value
                        FROM meta.ops_ci_search_terms
                        WHERE term_type IN ('drug_name', 'company_name')
                          AND is_active = TRUE
                        ORDER BY term_id
                        """
                    )
                    rows = cur.fetchall()

            terms = [row[0] for row in rows]
            if terms:
                logger.info("Loaded %d search terms from meta.ops_ci_search_terms", len(terms))
            return terms

        except Exception as e:
            logger.warning("Could not read search terms from DB: %s", e)
            return []

    def _search_filings(
        self,
        filing_type: str,
        *,
        sic_codes: List[str],
        days_back: int = 7,
        max_records: int = 5000,
        search_terms: Optional[List[str]] = None,
        skip_sic_filter: bool = False,
    ) -> List[Dict[str, Any]]:
        """Search EDGAR for filings of a specific type.

        Uses the `forms` parameter for form-type filtering (not q=formType:).
        When search_terms are provided (e.g. company name), searches for those
        instead of the generic "pharmaceutical" keyword.
        """
        records: List[Dict[str, Any]] = []
        date_from = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        date_to = datetime.utcnow().strftime("%Y-%m-%d")

        # Use first search term as query, or default to "pharmaceutical"
        # Wrap company names in quotes for exact entity matching
        if search_terms:
            query = f'"{search_terms[0]}"'
        else:
            query = "pharmaceutical"

        start = 0

        while len(records) < max_records:
            try:
                params = {
                    "q": query,
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
                    if record and (skip_sic_filter or self._is_pharma_company(record, sic_codes)):
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
            source.get("adsh")
            or source.get("accession_number")
            or source.get("accession_no")
            or hit.get("_id")
        )
        if not accession_number:
            return None

        accession_number = str(accession_number).strip()

        # Company info — handle both string and array fields
        display_names = source.get("display_names")
        if isinstance(display_names, list) and display_names:
            company_name = display_names[0]
        else:
            company_name = (
                source.get("company_name")
                or source.get("entity_name")
            )

        # CIK — handle array format
        ciks = source.get("ciks")
        if isinstance(ciks, list) and ciks:
            cik = str(ciks[0]).strip()
        else:
            cik = source.get("cik") or source.get("entity_id")
            if cik:
                cik = str(cik).strip()

        # Filing date
        filing_date = (
            source.get("file_date")
            or source.get("filing_date")
            or source.get("date_filed")
        )
        if filing_date:
            filing_date = str(filing_date)[:10]

        # Document URL
        document_url = source.get("file_url") or source.get("document_url")
        if not document_url and accession_number and cik:
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

        # SIC code — handle array format (sics)
        sics = source.get("sics")
        if isinstance(sics, list) and sics:
            sic = str(sics[0])
        else:
            sic = source.get("sic") or source.get("assigned_sic")

        record = {
            "accession_number": accession_number,
            "company_name": company_name,
            "cik": cik,
            "filing_type": filing_type,
            "filing_date": filing_date,
            "document_url": document_url,
            "description": description,
            "_sic": str(sic) if sic else None,
        }

        # Fetch MD&A text from the actual filing HTML
        if document_url and filing_type in ("10-K", "20-F", "10-K/A", "20-F/A"):
            mda_sections = self._fetch_mda_text(document_url, accession_number, cik)
            record.update(mda_sections)

        # Fetch structured XBRL financial facts (revenue, gross profit, R&D, net income).
        # Runs once per unique CIK — the fetcher deduplicates via _seen_xbrl_ciks so we
        # don't hammer the XBRL API for every filing from the same company.
        if cik and filing_type in ("10-K", "20-F", "10-K/A", "20-F/A"):
            if not hasattr(self, "_seen_xbrl_ciks"):
                self._seen_xbrl_ciks: set = set()
            if cik not in self._seen_xbrl_ciks:
                self._seen_xbrl_ciks.add(cik)
                xbrl = self._fetch_xbrl_facts_sync(cik)
                if xbrl:
                    record["xbrl_facts"] = xbrl

        return record

    def _fetch_xbrl_facts_sync(self, cik: str) -> dict:
        """Synchronous wrapper: fetch XBRL company facts via requests (no asyncio needed)."""
        try:
            cik_padded = str(cik).lstrip("0").zfill(10)
            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"
            time.sleep(SEC_REQUEST_DELAY)
            resp = self.session.get(url, timeout=30)
            if resp.status_code != 200:
                return {}

            data = resp.json()
            entity_name = data.get("entityName", "")
            facts = data.get("facts", {})

            taxonomy = "ifrs-full" if "ifrs-full" in facts else "us-gaap"
            tax_facts = facts.get(taxonomy, {})

            _REVENUE_TAGS = (
                "Revenue", "RevenueFromContractsWithCustomers", "RevenueFromSaleOfGoods",
                "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "SalesRevenueNet",
            )
            _GROSS_PROFIT_TAGS = ("GrossProfit",)
            _RD_TAGS = (
                "ResearchAndDevelopmentExpense",
                "ResearchAndDevelopmentExpenseRecognisedInProfitOrLoss",
            )
            _NET_INCOME_TAGS = (
                "ProfitLossAttributableToOwnersOfParent",
                "ProfitLossAttributableToOrdinaryEquityHoldersOfParentEntity",
                "ProfitLoss",
                "NetIncomeLoss",
            )

            def _series(tag_names):
                for tag in tag_names:
                    if tag not in tax_facts:
                        continue
                    usd_data = tax_facts[tag].get("units", {}).get("USD", [])
                    annual = [
                        r for r in usd_data
                        if r.get("fp") == "FY"
                        and r.get("form") in ("10-K", "20-F", "10-K/A", "20-F/A")
                    ]
                    if not annual:
                        continue
                    by_end: dict = {}
                    for r in annual:
                        end = r["end"]
                        if end not in by_end or r["filed"] > by_end[end]["filed"]:
                            by_end[end] = r
                    top = sorted(by_end.values(), key=lambda x: x["end"], reverse=True)[:5]
                    return [{"year": int(r["end"][:4]), "value_usd": r["val"]} for r in top]
                return []

            result = {
                "entity_name": entity_name,
                "taxonomy": taxonomy,
                "currency": "USD",
                "revenue_series": _series(_REVENUE_TAGS),
                "gross_profit_series": _series(_GROSS_PROFIT_TAGS),
                "rd_expense_series": _series(_RD_TAGS),
                "net_income_series": _series(_NET_INCOME_TAGS),
            }
            rev = result["revenue_series"]
            logger.info(
                "XBRL facts fetched for CIK %s (%s): %d revenue years%s",
                cik, entity_name, len(rev),
                f", latest ${rev[0]['value_usd']/1e9:.1f}B ({rev[0]['year']})" if rev else "",
            )
            return result

        except Exception as e:
            logger.debug("XBRL facts fetch failed for CIK %s: %s", cik, e)
            return {}

    def _fetch_mda_text(
        self, document_url: str, accession_number: str, cik: str
    ) -> dict:
        """Fetch and extract MD&A and Risk Factors text from a SEC filing.

        Finds the main HTML document in the filing index, fetches it,
        and extracts the Item 7 (MD&A) and Item 1A (Risk Factors) sections.

        For 20-F filers (foreign private issuers like AstraZeneca), the main filing
        often contains only "incorporated by reference" boilerplate pointing to the
        Annual Report (Exhibit 15.1). In that case, we fetch Exhibit 15.1 directly —
        which may be HTML or PDF — and extract from it instead.

        Returns a dict with mda_text and risk_factors_text keys (empty strings on failure).
        """
        empty = {"mda_text": "", "risk_factors_text": ""}
        try:
            from dk_data.services.external_apis.sec_edgar_client import SECEdgarClient

            acc_clean = accession_number.replace("-", "")
            index_url = (
                f"{SEC_ARCHIVES_URL}/Archives/edgar/data/{cik}/{acc_clean}/{accession_number}-index.htm"
            )
            time.sleep(SEC_REQUEST_DELAY)
            index_resp = self.session.get(index_url, timeout=15)
            doc_html_url = None
            filing_documents: list = []

            if index_resp.status_code == 200:
                filing_documents = self._parse_filing_index(index_resp.text, cik, acc_clean)

                # Find main filing document (20-F or 10-K)
                main_types = {"20-F", "10-K", "20-F/A", "10-K/A"}
                main_docs = [d for d in filing_documents if d.get("type", "").upper() in main_types]
                if main_docs:
                    doc_html_url = main_docs[0]["url"]
                else:
                    matches = re.findall(
                        r'href="([^"]+\.htm)"[^>]*>(?:10-K|20-F|Annual Report)',
                        index_resp.text, re.IGNORECASE
                    )
                    if not matches:
                        matches = re.findall(r'href="(/Archives/edgar/data/[^"]+\.htm)"', index_resp.text)
                    if matches:
                        href = matches[0]
                        doc_html_url = (
                            href if href.startswith("http") else f"{SEC_ARCHIVES_URL}{href}"
                        )

            if not doc_html_url:
                doc_html_url = f"{SEC_ARCHIVES_URL}/Archives/edgar/data/{cik}/{acc_clean}/{acc_clean}.htm"

            time.sleep(SEC_REQUEST_DELAY)
            doc_resp = self.session.get(doc_html_url, timeout=30)
            if doc_resp.status_code != 200:
                logger.debug(
                    "SEC HTML fetch failed for %s: HTTP %s", accession_number, doc_resp.status_code
                )
                return empty

            client = SECEdgarClient.__new__(SECEdgarClient)
            result = client.extract_mda_sections(doc_resp.text)

            # 20-F filers (e.g. AstraZeneca, Roche, Novartis) often use
            # "incorporated by reference" in the main filing, with the actual
            # financial data living in Exhibit 15.1 (the Annual Report PDF/HTML).
            # Detect this pattern and fall back to fetching the exhibit directly.
            if self._is_incorporated_by_reference(result.get("mda_text", "")):
                exhibit_result = self._fetch_exhibit_15_1(filing_documents, client)
                if exhibit_result.get("mda_text"):
                    logger.info(
                        "SEC %s: replaced boilerplate MD&A with Exhibit 15.1 text (%d chars)",
                        accession_number, len(exhibit_result["mda_text"]),
                    )
                    result = exhibit_result

            return result

        except Exception as e:
            logger.debug("MD&A extraction failed for %s: %s", accession_number, e)
            return empty

    @staticmethod
    def _is_incorporated_by_reference(mda_text: str) -> bool:
        """Return True when MD&A text is boilerplate 'incorporated by reference' with no financials."""
        if not mda_text:
            return True
        has_ibr = bool(re.search(
            r"incorporated\s+(?:herein\s+)?by\s+reference", mda_text, re.IGNORECASE
        ))
        has_financials = bool(re.search(
            r"\$\s*\d+(?:\.\d+)?\s*(?:billion|million|bn|m\b|\d)|"
            r"\b\d+(?:\.\d+)?\s*(?:billion|million)\b",
            mda_text, re.IGNORECASE
        ))
        return has_ibr and not has_financials

    def _parse_filing_index(self, index_html: str, cik: str, acc_clean: str) -> list:
        """Parse filing index HTML into a list of {url, type, description} dicts."""
        docs = []
        rows = re.findall(r"<tr[^>]*>.*?</tr>", index_html, re.DOTALL | re.IGNORECASE)
        for row in rows:
            href_match = re.search(
                r'href="(/Archives/edgar/data/[^"]+)"', row, re.IGNORECASE
            )
            if not href_match:
                continue
            url = f"{SEC_ARCHIVES_URL}{href_match.group(1)}"
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
            doc_type = re.sub(r"<[^>]+>", "", cells[1]).strip() if len(cells) > 1 else ""
            description = re.sub(r"<[^>]+>", "", cells[2]).strip() if len(cells) > 2 else ""
            docs.append({"url": url, "type": doc_type, "description": description})
        return docs

    def _fetch_exhibit_15_1(self, filing_documents: list, client) -> dict:
        """Fetch Exhibit 15.1 (Annual Report) and extract MD&A text from it.

        Handles both HTML and PDF exhibits. PDF is common for foreign private issuers
        (e.g. AstraZeneca, Roche) that attach their full Annual Report as exhibit 15.1.
        """
        empty = {"mda_text": "", "risk_factors_text": ""}

        exhibit_url = None
        for doc in filing_documents:
            doc_type = doc.get("type", "").upper()
            if doc_type in ("EX-15.1", "EX-15", "EX-15.01", "EX-13"):
                exhibit_url = doc["url"]
                break

        if not exhibit_url:
            return empty

        try:
            time.sleep(SEC_REQUEST_DELAY)
            resp = self.session.get(exhibit_url, timeout=90)
            if resp.status_code != 200:
                return empty

            content_type = resp.headers.get("content-type", "").lower()
            is_pdf = "pdf" in content_type or exhibit_url.lower().endswith(".pdf")

            if is_pdf:
                return self._extract_mda_from_pdf(resp.content, client)
            else:
                return client.extract_mda_sections(resp.text)

        except Exception as e:
            logger.debug("Exhibit 15.1 fetch/parse failed (%s): %s", exhibit_url, e)
            return empty

    @staticmethod
    def _extract_mda_from_pdf(pdf_bytes: bytes, client) -> dict:
        """Extract MD&A text from a PDF Annual Report using pypdf."""
        empty = {"mda_text": "", "risk_factors_text": ""}
        try:
            import io
            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            pages_text = []
            for page in reader.pages:
                text = page.extract_text() or ""
                if text.strip():
                    pages_text.append(text)

            if not pages_text:
                return empty

            full_text = "\n".join(pages_text)
            # BeautifulSoup on plain text is a no-op (no tags to strip), so we can
            # pass the extracted text straight into the existing section extractor.
            return client.extract_mda_sections(full_text)

        except ImportError:
            logger.warning(
                "pypdf not installed — cannot extract text from PDF exhibit; "
                "add pypdf>=4.0.0 to pyproject.toml dependencies"
            )
            return empty
        except Exception as e:
            logger.debug("PDF MD&A extraction failed: %s", e)
            return empty

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

