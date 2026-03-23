"""
SEC EDGAR API Client.

Fetch SEC annual filings and extract MD&A section text for the xenon
assessment pipeline. Revenue extraction from MD&A text is handled
downstream by xenon's LLM pre-aggregation step
(processFinancialFilingsWithLLM in assessment-orchestrator.service.ts).

FREE - US Government public data.
API Documentation: https://www.sec.gov/edgar/sec-api-documentation
Rate Limit: 10 requests per second (strictly enforced)

Responsibilities:
1. Look up a company's CIK by name (tickers.json + browse-edgar fallback)
2. Enumerate recent annual filings (10-K / 20-F)
3. Extract the MD&A text section from a filing's HTML
"""

import os
import re
from datetime import datetime
from typing import Dict, List, Optional

from bs4 import BeautifulSoup
from loguru import logger

from .base_client import APIClientConfig, BaseAPIClient
from .sec_rate_limiter import SECRateLimiter
from ...models.market_intelligence import Filing


class SECEdgarClient(BaseAPIClient):
    """
    Fetch SEC filings and extract MD&A section text.

    Revenue extraction is handled downstream by xenon's LLM pipeline —
    no table parsing, no hardcoded heuristics, no revenue columns here.
    """

    BASE_URL = "https://data.sec.gov"
    ARCHIVES_URL = "https://www.sec.gov"

    def __init__(self, config: Optional[APIClientConfig] = None):
        """Initialize SEC EDGAR client with rate limiting."""
        user_agent = os.getenv(
            "SEC_EDGAR_USER_AGENT",
            "DataKinetic Drug Intelligence Platform (contact@datakinetic.com)"
        )

        if config is None:
            config = APIClientConfig(
                base_url=self.BASE_URL,
                timeout=30.0,
                max_retries=3,
                cache_ttl=7 * 24 * 3600,  # 7 days (annual filings)
                headers={
                    "User-Agent": user_agent,
                    "Accept": "application/json, text/html, */*",
                },
            )

        super().__init__(config, cache_manager=None)

        self.user_agent = user_agent
        self.headers = {
            "User-Agent": user_agent,
            "Accept": "application/json, text/html, */*",
        }

        self.rate_limiter = SECRateLimiter(requests_per_second=10.0)

    async def health_check(self) -> bool:
        """Check if SEC EDGAR API is accessible."""
        try:
            client = await self._get_client()
            response = await client.get("/", timeout=5.0)
            return response.status_code < 500
        except Exception:
            return False

    async def get_company_filings(
        self,
        cik: str,
        filing_type: str = "10-K",
        years: int = 5,
    ) -> List[Filing]:
        """
        Get recent annual filings for a company.

        Args:
            cik: SEC Central Index Key
            filing_type: "10-K" or "20-F"
            years: Number of years of filings to retrieve

        Returns:
            List of Filing objects sorted newest-first.
        """
        await self.rate_limiter.acquire()

        cik_padded = cik.zfill(10)
        try:
            data = await super()._get(f"/submissions/CIK{cik_padded}.json")

            filings: List[Filing] = []
            recent = data.get("filings", {}).get("recent", {})

            forms = recent.get("form", [])
            accession_numbers = recent.get("accessionNumber", [])
            filing_dates = recent.get("filingDate", [])

            for i, form in enumerate(forms):
                if form == filing_type and i < len(accession_numbers) and i < len(filing_dates):
                    filing_date = datetime.strptime(filing_dates[i], "%Y-%m-%d").date()
                    accession = accession_numbers[i]
                    accession_clean = accession.replace("-", "")
                    filings.append(Filing(
                        accession=accession,
                        filing_date=filing_date,
                        form=form,
                        document_url=f"{self.BASE_URL}/Archives/edgar/data/{cik}/{accession_clean}",
                        company_cik=cik,
                    ))

            filings.sort(key=lambda x: x.filing_date, reverse=True)
            return filings[:years]

        except Exception as e:
            logger.error(f"Error fetching filings for CIK {cik}: {e}")
            return []

    def extract_mda_sections(self, filing_html: str) -> Dict[str, str]:
        """
        Extract MD&A and Risk Factors sections from 10-K/20-F filing HTML.

        Returns raw text — revenue extraction from this text is the
        responsibility of xenon's LLM (processFinancialFilingsWithLLM).

        Args:
            filing_html: Raw HTML content of the filing

        Returns:
            Dict with 'mda_text' and 'risk_factors_text' keys (up to 5000 chars each).
        """
        result = {"mda_text": "", "risk_factors_text": ""}
        if not filing_html:
            return result

        full_text = BeautifulSoup(filing_html, "html.parser").get_text()
        full_text = re.sub(r"[ \t]+", " ", full_text)
        full_text = re.sub(r"\n{3,}", "\n\n", full_text)

        mda_start_patterns = [
            r"(?i)item\s*7[\.\s:]*\s*management.s\s+discussion\s+and\s+analysis",
            r"(?i)item\s*7[\.\s]*\s*management.s\s+discussion",
            r"(?i)item\s*7[\.\s:]+\s*md\s*&\s*a",
            r"(?i)management.s\s+discussion\s+and\s+analysis\s+of\s+financial\s+condition",
            r"(?i)management.s\s+discussion\s+and\s+analysis",
            r"(?i)item\s*5[\.\s:]*\s*operating\s+and\s+financial\s+review",  # 20-F
        ]
        mda_end_patterns = [
            r"(?i)item\s*7a[\.\s:]*\s*quantitative\s+and\s+qualitative",
            r"(?i)item\s*8[\.\s:]*\s*financial\s+statements",
            r"(?i)item\s*6[\.\s:]*\s*directors",  # 20-F: Item 6 follows Item 5
        ]

        mda_text = self._extract_section(full_text, mda_start_patterns, mda_end_patterns)
        if mda_text:
            result["mda_text"] = mda_text[:5000]

        risk_start_patterns = [
            r"(?i)item\s*1a[\.\s:]*\s*risk\s+factors",
            r"(?i)item\s*3[\.\s:]*\s*(?:key\s+information.*)?risk\s+factors",  # 20-F Item 3D
            r"(?i)risk\s+factors",
        ]
        risk_end_patterns = [
            r"(?i)item\s*1b[\.\s:]*\s*unresolved\s+staff\s+comments",
            r"(?i)item\s*2[\.\s:]*\s*(?:properties|description\s+of\s+property)",
            r"(?i)item\s*4[\.\s:]*\s*(?:information\s+on\s+the\s+company|mine\s+safety)",
        ]

        risk_text = self._extract_section(full_text, risk_start_patterns, risk_end_patterns)
        if risk_text:
            result["risk_factors_text"] = risk_text[:5000]

        return result

    def _extract_section(
        self,
        full_text: str,
        start_patterns: List[str],
        end_patterns: List[str],
    ) -> Optional[str]:
        """Extract a section of text between matching start and end patterns."""
        candidate_starts = []
        for pattern in start_patterns:
            for match in re.finditer(pattern, full_text):
                candidate_starts.append(match.start())

        if not candidate_starts:
            return None

        best_section = None
        for start_idx in sorted(set(candidate_starts)):
            search_from = start_idx + 200  # skip past the section header itself
            end_idx = None
            for pattern in end_patterns:
                match = re.search(pattern, full_text[search_from:])
                if match:
                    candidate = search_from + match.start()
                    if end_idx is None or candidate < end_idx:
                        end_idx = candidate

            if end_idx is None:
                end_idx = min(start_idx + 15000, len(full_text))

            section = full_text[start_idx:end_idx].strip()
            if len(section) > 200:
                if best_section is None or len(section) > len(best_section):
                    best_section = section
                if len(section) > 1000:
                    break

        return best_section

    async def lookup_cik_by_company_name(self, company_name: str) -> Optional[str]:
        """
        Look up a company's SEC CIK by name.

        Strategy (two-tier):
        1. SEC company_tickers.json — authoritative CIK→name mapping for all
           registered US SEC filers. Matches by first meaningful word in company_name.
        2. EDGAR browse-edgar Atom endpoint (fallback) — prefix name search.

        Returns:
            CIK string (no leading zeros) or None if not found.
        """
        import re as _re
        import urllib.parse
        import xml.etree.ElementTree as ET

        words = _re.split(r"[\s\-]+", company_name.strip())
        _GENERIC = {
            "pharmaceuticals", "pharmaceutical", "pharma", "corporation", "incorporated",
            "inc", "ltd", "limited", "ag", "as", "plc", "co", "company", "holding",
            "holdings", "group", "international", "and", "the", "biosciences",
            "biopharmaceuticals", "therapeutics", "sciences",
        }
        search_tokens = [
            w.lower() for w in words
            if len(w) > 2 and w.lower() not in _GENERIC
        ][:2]
        client = await self._get_client()

        # ── Tier 1: company_tickers.json ────────────────────────────────────────
        try:
            await self.rate_limiter.acquire()
            tickers_resp = await client.get(
                "https://www.sec.gov/files/company_tickers.json",
                headers=self.headers,
            )
            if tickers_resp.status_code == 200:
                tickers = tickers_resp.json()
                best_cik: Optional[str] = None
                best_title: Optional[str] = None
                for entry in tickers.values():
                    title_lower = entry.get("title", "").lower()
                    title_words = set(_re.split(r"[\s\-/&,\.]+", title_lower))
                    if search_tokens and all(tok in title_words for tok in search_tokens):
                        cik_candidate = str(entry["cik_str"])
                        await self.rate_limiter.acquire()
                        sub_resp = await client.get(
                            f"https://data.sec.gov/submissions/CIK{cik_candidate.zfill(10)}.json",
                            headers=self.headers,
                        )
                        if sub_resp.status_code != 200:
                            continue
                        sub_data = sub_resp.json()
                        forms = sub_data.get("filings", {}).get("recent", {}).get("form", [])
                        if any(f in ("10-K", "20-F", "10-K/A", "20-F/A") for f in forms):
                            best_cik = cik_candidate
                            best_title = sub_data.get("name", entry.get("title"))
                            break
                if best_cik:
                    logger.info(
                        f"SEC EDGAR CIK lookup (tickers): '{company_name}'"
                        f" → CIK {best_cik} ({best_title})"
                    )
                    return best_cik
        except Exception as e:
            logger.debug(f"CIK lookup via company_tickers.json failed: {e}")

        # ── Tier 2: browse-edgar prefix search (fallback) ────────────────────────
        EDGAR_CGI = "https://www.sec.gov/cgi-bin/browse-edgar"
        ATOM_NS = "http://www.w3.org/2005/Atom"

        seen: set = set()
        variants: List[str] = []
        for candidate in [
            company_name,
            " ".join(words[:2]) if len(words) >= 2 else None,
            words[0] if words else None,
        ]:
            if candidate and candidate.lower() not in seen:
                seen.add(candidate.lower())
                variants.append(candidate)

        for variant in variants:
            try:
                encoded = urllib.parse.quote_plus(variant)
                url = (
                    f"{EDGAR_CGI}?company={encoded}"
                    f"&action=getcompany&type="
                    f"&owner=include&count=20&output=atom"
                )
                await self.rate_limiter.acquire()
                response = await client.get(url, headers=self.headers)
                if response.status_code != 200:
                    continue

                root = ET.fromstring(response.text)
                for entry in root.findall(f"{{{ATOM_NS}}}entry"):
                    cik_candidate = None
                    content = entry.find(f"{{{ATOM_NS}}}content")
                    if content is not None:
                        ci = content.find(f"{{{ATOM_NS}}}company-info")
                        if ci is not None:
                            cik_elem = ci.find(f"{{{ATOM_NS}}}cik")
                            if cik_elem is not None and cik_elem.text:
                                cik_candidate = str(int(cik_elem.text.strip()))
                    if not cik_candidate:
                        id_elem = entry.find(f"{{{ATOM_NS}}}id")
                        if id_elem is not None and id_elem.text:
                            m = _re.search(r"cik=0*(\d+)", id_elem.text)
                            if m:
                                cik_candidate = m.group(1)
                    if not cik_candidate:
                        continue

                    await self.rate_limiter.acquire()
                    sub_resp = await client.get(
                        f"https://data.sec.gov/submissions/CIK{cik_candidate.zfill(10)}.json",
                        headers=self.headers,
                    )
                    if sub_resp.status_code != 200:
                        continue
                    sub_data = sub_resp.json()
                    forms = sub_data.get("filings", {}).get("recent", {}).get("form", [])
                    if not any(f in ("10-K", "20-F", "10-K/A", "20-F/A") for f in forms):
                        logger.debug(
                            f"CIK {cik_candidate} ({sub_data.get('name', '?')}) has no annual filings — skipping"
                        )
                        continue
                    entity_name = sub_data.get("name", cik_candidate)
                    logger.info(
                        f"SEC EDGAR CIK lookup (browse-edgar): '{variant}'"
                        f" → CIK {cik_candidate} ({entity_name})"
                    )
                    return cik_candidate

            except Exception as e:
                logger.debug(f"CIK lookup (browse-edgar) error for '{variant}': {e}")
                continue

        logger.warning(
            f"SEC EDGAR CIK lookup: no annual-filing entity found for '{company_name}'"
        )
        return None
