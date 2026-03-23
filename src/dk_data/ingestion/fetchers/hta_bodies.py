"""HTA Bodies Decision Fetcher.

Feature: 011-datasource-integration
Task: T058-T060 — HTA Bodies CI source integration

Fetches technology appraisal decisions from Health Technology Assessment
(HTA) bodies.  Implements NICE (UK), G-BA (Germany), HAS (France),
and PBAC (Australia) via web scraping.

Query-scoped from meta.ops_ci_search_terms WHERE term_type = 'drug_name'.
Weekly cadence.

Sources:
- NICE: https://www.nice.org.uk/guidance/published?type=ta
- G-BA: https://www.g-ba.de/bewertungsverfahren/nutzenbewertung/
- HAS: https://www.has-sante.fr/
- PBAC: https://www.pbs.gov.au/pbs/industry/listing/elements/pbac-meetings
"""

import hashlib
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# NICE search and guidance URLs (structured API is deprecated, use HTML scraping)
NICE_SEARCH_URL = "https://www.nice.org.uk/Search"
NICE_GUIDANCE_BASE = "https://www.nice.org.uk/guidance"

# Agency identifiers
AGENCIES = ["nice", "gba", "has", "pbac"]


class HTABodiesFetcher(BaseFetcher):
    """Fetcher for HTA body decisions (multi-agency CI scope)."""

    SOURCE_NAME = "hta_bodies"
    BASE_URL = "https://www.nice.org.uk"

    def get_latest_url(self) -> str:
        """Return the NICE guidance search URL."""
        return NICE_SEARCH_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch HTA decisions from all configured agencies.

        Keyword Args:
            days_back: Number of days to look back (default: 7).
            drug_names: Optional list of drug name strings to search.
                        If not provided, reads from DB.
            agencies: Optional list of agency codes (default: all).

        Returns:
            Dict with keys: status, records, hash, error (on failure).
        """
        days_back = kwargs.get("days_back", 7)
        agencies = kwargs.get("agencies", AGENCIES)

        try:
            drug_names = kwargs.get("drug_names") or self._get_drug_names()

            if not drug_names:
                # Default fallback terms when meta.ops_ci_search_terms is empty
                drug_names = [
                    "dupilumab",
                    "semaglutide",
                    "pembrolizumab",
                    "adalimumab",
                    "nivolumab",
                ]
                logger.info(
                    "No drug names from DB; using %d default pharma terms",
                    len(drug_names),
                )

            logger.info(
                "Fetching HTA decisions (days_back=%d, agencies=%s, drugs=%d)",
                days_back, agencies, len(drug_names),
            )

            all_records: List[Dict[str, Any]] = []
            seen_ids: set = set()

            for agency in agencies:
                try:
                    records = self._fetch_agency(
                        agency,
                        drug_names=drug_names,
                        days_back=days_back,
                    )
                    for record in records:
                        decision_id = record.get("decision_id")
                        if decision_id and decision_id not in seen_ids:
                            seen_ids.add(decision_id)
                            all_records.append(record)
                except Exception as e:
                    logger.warning(
                        "Failed to fetch from %s: %s", agency, e
                    )
                    continue

            # Compute content hash
            content_hash = hashlib.md5(
                ",".join(sorted(seen_ids)).encode()
            ).hexdigest() if seen_ids else None

            self.save_manifest(
                last_run_at=datetime.now(timezone.utc).isoformat(),
                last_run_status="completed",
                total_records_fetched=len(all_records),
                last_content_hash=content_hash,
            )

            result: Dict[str, Any] = {
                "status": "success",
                "records": all_records,
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(all_records)})
            return result

        except Exception as e:
            logger.exception("HTA bodies fetch failed: %s", e)
            self.save_manifest(last_run_status="interrupted")
            result = {
                "status": "failed",
                "records": [],
                "hash": None,
                "error": str(e),
            }
            self.log_fetch_result(result)
            return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_drug_names(self) -> List[str]:
        """Read drug names from meta.ops_ci_search_terms.

        Returns:
            List of drug name strings.
        """
        try:
            from ..utils.database import get_connection

            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT term_value
                        FROM meta.ops_ci_search_terms
                        WHERE term_type = 'drug_name'
                          AND is_active = TRUE
                        ORDER BY term_id
                        """
                    )
                    rows = cur.fetchall()

            names = [row[0] for row in rows]
            if names:
                logger.info(
                    "Loaded %d drug names from meta.ops_ci_search_terms",
                    len(names),
                )
            return names

        except Exception as e:
            logger.warning(
                "Could not read drug names from DB: %s", e
            )
            return []

    def _fetch_agency(
        self,
        agency: str,
        *,
        drug_names: List[str],
        days_back: int = 7,
    ) -> List[Dict[str, Any]]:
        """Dispatch fetch to the appropriate agency handler.

        Args:
            agency: Agency code (nice, gba, has, pbac).
            drug_names: Drug names to search for.
            days_back: Look-back window in days.

        Returns:
            List of normalized decision record dicts.
        """
        dispatch = {
            "nice": self._fetch_nice,
            "gba": self._fetch_gba,
            "has": self._fetch_has,
            "pbac": self._fetch_pbac,
        }
        handler = dispatch.get(agency)
        if handler is None:
            logger.warning("Unknown HTA agency: %s", agency)
            return []
        return handler(drug_names=drug_names, days_back=days_back)

    # ------------------------------------------------------------------
    # NICE (UK) — primary implementation
    # ------------------------------------------------------------------

    # Decision classification patterns for NICE recommendation text
    NICE_DECISION_PATTERNS = [
        ("Not recommended", ["is not recommended", "are not recommended"]),
        ("Recommended (CDF)", ["cancer drugs fund", "cdf"]),
        ("Recommended (managed access)", ["managed access"]),
        ("Recommended", [
            "is recommended", "are recommended", "recommended as an option",
            "recommended, within", "recommended for use",
        ]),
        ("Recommended (conditional)", ["can be used", "should be used"]),
        ("Terminated", ["terminated"]),
    ]

    def _fetch_nice(
        self,
        *,
        drug_names: List[str],
        days_back: int = 7,
    ) -> List[Dict[str, Any]]:
        """Fetch NICE technology appraisal decisions by scraping HTML pages.

        For each drug name, searches the NICE website for technology appraisals,
        then scrapes individual TA recommendation pages for structured data.

        Args:
            drug_names: Drug names to search for.
            days_back: Look-back window in days.

        Returns:
            List of normalized HTA decision dicts.
        """
        since_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        records: List[Dict[str, Any]] = []
        seen_ta_ids: set = set()

        for drug_name in drug_names:
            # Step 1: Search NICE for this drug to find TA guidance IDs
            try:
                resp = requests.get(
                    NICE_SEARCH_URL,
                    params={"q": drug_name, "ps": "20", "sp": "on"},
                    headers={"User-Agent": "DK-Data-Platform/1.0 (Research)"},
                    timeout=30,
                )
                resp.raise_for_status()
                time.sleep(1)  # respectful crawling
            except Exception as e:
                logger.debug("NICE search for '%s' failed: %s", drug_name, e)
                continue

            # Extract TA guidance IDs from search results
            ta_ids = re.findall(r'/guidance/(ta\d+)', resp.text, re.IGNORECASE)
            ta_ids = list(dict.fromkeys(ta_ids))  # deduplicate, preserve order

            if not ta_ids:
                logger.debug("No NICE TAs found for '%s'", drug_name)
                continue

            # Step 2: Scrape each TA recommendation page
            for ta_id in ta_ids:
                if ta_id.lower() in seen_ta_ids:
                    continue
                seen_ta_ids.add(ta_id.lower())

                record = self._scrape_nice_ta(ta_id, drug_name, since_date)
                if record:
                    records.append(record)
                time.sleep(1)  # respectful crawling

        logger.info("Fetched %d NICE TA decisions", len(records))
        return records

    def _scrape_nice_ta(
        self,
        ta_id: str,
        drug_name: str,
        since_date: datetime,
    ) -> Optional[Dict[str, Any]]:
        """Scrape an individual NICE TA recommendation page.

        Args:
            ta_id: Guidance ID (e.g., 'ta798').
            drug_name: Drug name for context.
            since_date: Only return if published after this date.

        Returns:
            Normalized decision dict, or None if not relevant.
        """
        url = f"{NICE_GUIDANCE_BASE}/{ta_id}/chapter/1-Recommendations"

        try:
            resp = requests.get(
                url,
                headers={"User-Agent": "DK-Data-Platform/1.0 (Research)"},
                timeout=30,
                allow_redirects=True,
            )
            if resp.status_code != 200:
                logger.debug("NICE %s: HTTP %d", ta_id, resp.status_code)
                return None

            html = resp.text
            soup = BeautifulSoup(html, "html.parser")

            # Extract title
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else ta_id

            # Extract publication date from <time datetime="...">
            decision_date = None
            time_tag = soup.find("time", attrs={"datetime": True})
            if time_tag:
                decision_date = time_tag["datetime"][:10]

            # Filter by date if available
            if decision_date and since_date:
                try:
                    pub_dt = datetime.strptime(decision_date, "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    )
                    if pub_dt < since_date:
                        return None
                except ValueError:
                    pass

            # Extract recommendation text from the page body
            # Strip tags and normalize whitespace for text extraction
            body_text = re.sub(r'<[^>]+>', ' ', html)
            body_text = re.sub(r'\s+', ' ', body_text).strip()

            # Find section 1.1 recommendation text
            rec_text = ""
            rec_match = re.search(
                r'1\.1\s+(.{50,}?)(?:1\.2\s|\b2\s+[A-Z]|The committee|Evidence|Why the committee|$)',
                body_text,
                re.DOTALL,
            )
            if rec_match:
                rec_text = rec_match.group(1).strip()
            else:
                idx = body_text.find('1.1 ')
                if idx >= 0:
                    rec_text = body_text[idx + 4:idx + 504].strip()

            # Classify the decision
            decision_type = self._classify_nice_decision(rec_text)

            # Extract indication from recommendation text
            indication = self._extract_nice_indication(rec_text)

            return {
                "decision_id": f"nice-{ta_id.upper()}",
                "agency": "nice",
                "drug_name": drug_name,
                "indication": indication,
                "decision_type": decision_type,
                "decision_date": decision_date,
                "document_url": f"{NICE_GUIDANCE_BASE}/{ta_id}",
                "summary": (rec_text[:300] if rec_text else title),
            }

        except Exception as e:
            logger.debug("NICE %s scrape failed: %s", ta_id, e)
            return None

    def _classify_nice_decision(self, recommendation_text: str) -> Optional[str]:
        """Classify NICE decision from recommendation text."""
        lower = recommendation_text.lower()
        for label, patterns in self.NICE_DECISION_PATTERNS:
            if any(p in lower for p in patterns):
                return label
        return "Unknown" if recommendation_text else None

    @staticmethod
    def _extract_nice_indication(recommendation_text: str) -> Optional[str]:
        """Extract indication from NICE recommendation sentence."""
        patterns = [
            r'(?:for treating|for the treatment of|as an option for|for use in)\s+(.+?)(?:\s+in adults|\s+if|\s+only|\s+when|\.\s)',
            r'(?:for|treating)\s+((?:locally |advanced |unresectable |metastatic )*\w[\w\s\-]+(?:cancer|carcinoma|lymphoma|leukaemia|leukemia|melanoma|myeloma|sarcoma|glioma|mesothelioma))',
        ]
        for pat in patterns:
            m = re.search(pat, recommendation_text, re.IGNORECASE)
            if m:
                indication = m.group(1).strip()
                indication = re.sub(
                    r'\s+(in|if|only|when|that|whose|after|following)$',
                    '', indication, flags=re.IGNORECASE,
                )
                return indication[:200]
        return None

    # ------------------------------------------------------------------
    # G-BA (Germany) — Nutzenbewertung scraper
    # ------------------------------------------------------------------

    GBA_URL = "https://www.g-ba.de/bewertungsverfahren/nutzenbewertung/"
    GBA_DECISION_MAP = {
        "zusatznutzen belegt": "Benefit proven",
        "zusatznutzen nicht belegt": "Benefit not proven",
        "geringerer nutzen": "Lesser benefit",
        "nicht quantifizierbar": "Not quantifiable",
        "beträchtlich": "Considerable benefit",
        "erheblich": "Major benefit",
        "gering": "Minor benefit",
    }

    def _fetch_gba(
        self, *, drug_names: List[str], days_back: int = 7
    ) -> List[Dict[str, Any]]:
        """Fetch G-BA Nutzenbewertung decisions by scraping the listing page."""
        since_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        drug_names_lower = [d.lower() for d in drug_names] if drug_names else []
        records: List[Dict[str, Any]] = []

        try:
            resp = requests.get(
                self.GBA_URL,
                headers={"User-Agent": "DK-Data-Platform/1.0 (Research)"},
                timeout=30,
            )
            resp.raise_for_status()
            time.sleep(1)  # respectful crawling

            soup = BeautifulSoup(resp.text, "html.parser")

            for row in soup.select("table tr, .bewertung-item, .list-item, article"):
                text = row.get_text(separator=" ", strip=True)
                if not text:
                    continue

                # Try to extract a date from the row
                date_str = self._extract_date_from_text(text)
                if date_str:
                    try:
                        decision_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                        if decision_date < since_date:
                            continue
                    except ValueError:
                        pass

                # Check if any drug name matches
                text_lower = text.lower()
                if drug_names_lower and not any(dn in text_lower for dn in drug_names_lower):
                    continue

                # Extract decision type
                decision_type = None
                for gba_key, eng_val in self.GBA_DECISION_MAP.items():
                    if gba_key in text_lower:
                        decision_type = eng_val
                        break

                # Extract link
                link_tag = row.find("a", href=True)
                doc_url = None
                if link_tag:
                    href = link_tag["href"]
                    doc_url = href if href.startswith("http") else f"https://www.g-ba.de{href}"

                drug_name = self._match_drug_name(text, drug_names) or text[:80]
                decision_id = f"gba-{hashlib.md5(text[:120].encode()).hexdigest()[:12]}"

                records.append({
                    "decision_id": decision_id,
                    "agency": "gba",
                    "drug_name": drug_name,
                    "indication": None,
                    "decision_type": decision_type,
                    "decision_date": date_str,
                    "document_url": doc_url,
                    "summary": text[:300],
                })

        except Exception as e:
            logger.warning("G-BA scraping failed: %s", e)

        logger.info("Fetched %d G-BA decisions", len(records))
        return records

    # ------------------------------------------------------------------
    # HAS (France) — Transparency Committee scraper
    # ------------------------------------------------------------------

    HAS_URL = "https://www.has-sante.fr/jcms/fc_2875171/en/transparency-committee"

    def _fetch_has(
        self, *, drug_names: List[str], days_back: int = 7
    ) -> List[Dict[str, Any]]:
        """Fetch HAS transparency committee opinions."""
        since_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        drug_names_lower = [d.lower() for d in drug_names] if drug_names else []
        records: List[Dict[str, Any]] = []

        try:
            resp = requests.get(
                self.HAS_URL,
                headers={
                    "User-Agent": "DK-Data-Platform/1.0 (Research)",
                    "Accept-Language": "en",
                },
                timeout=30,
            )
            resp.raise_for_status()
            time.sleep(1)

            soup = BeautifulSoup(resp.text, "html.parser")

            for item in soup.select(".publication-item, .list-item, article, table tr"):
                text = item.get_text(separator=" ", strip=True)
                if not text:
                    continue

                date_str = self._extract_date_from_text(text)
                if date_str:
                    try:
                        decision_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                        if decision_date < since_date:
                            continue
                    except ValueError:
                        pass

                text_lower = text.lower()
                if drug_names_lower and not any(dn in text_lower for dn in drug_names_lower):
                    continue

                # Determine decision type
                decision_type = None
                if "favorable" in text_lower and "unfavorable" not in text_lower:
                    decision_type = "Favorable"
                elif "unfavorable" in text_lower or "unfavourable" in text_lower:
                    decision_type = "Unfavorable"
                elif "conditional" in text_lower:
                    decision_type = "Conditional"

                link_tag = item.find("a", href=True)
                doc_url = None
                if link_tag:
                    href = link_tag["href"]
                    doc_url = href if href.startswith("http") else f"https://www.has-sante.fr{href}"

                drug_name = self._match_drug_name(text, drug_names) or text[:80]
                decision_id = f"has-{hashlib.md5(text[:120].encode()).hexdigest()[:12]}"

                records.append({
                    "decision_id": decision_id,
                    "agency": "has",
                    "drug_name": drug_name,
                    "indication": None,
                    "decision_type": decision_type,
                    "decision_date": date_str,
                    "document_url": doc_url,
                    "summary": text[:300],
                })

        except Exception as e:
            logger.warning("HAS scraping failed: %s", e)

        logger.info("Fetched %d HAS decisions", len(records))
        return records

    # ------------------------------------------------------------------
    # PBAC (Australia) — Meeting Outcomes scraper
    # ------------------------------------------------------------------

    PBAC_URL = "https://www.pbs.gov.au/info/industry/listing/elements/pbac-meetings/pbac-outcomes"

    def _fetch_pbac(
        self, *, drug_names: List[str], days_back: int = 7
    ) -> List[Dict[str, Any]]:
        """Fetch PBAC meeting outcome decisions."""
        since_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        drug_names_lower = [d.lower() for d in drug_names] if drug_names else []
        records: List[Dict[str, Any]] = []

        try:
            resp = requests.get(
                self.PBAC_URL,
                headers={"User-Agent": "DK-Data-Platform/1.0 (Research)"},
                timeout=30,
            )
            resp.raise_for_status()
            time.sleep(0.5)  # 2 req/s

            soup = BeautifulSoup(resp.text, "html.parser")

            for row in soup.select("table tr, .outcome-item, article, .list-item"):
                text = row.get_text(separator=" ", strip=True)
                if not text:
                    continue

                date_str = self._extract_date_from_text(text)
                if date_str:
                    try:
                        decision_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                        if decision_date < since_date:
                            continue
                    except ValueError:
                        pass

                text_lower = text.lower()
                if drug_names_lower and not any(dn in text_lower for dn in drug_names_lower):
                    continue

                decision_type = None
                if "recommended" in text_lower and "not recommended" not in text_lower:
                    decision_type = "Recommended"
                elif "not recommended" in text_lower:
                    decision_type = "Not recommended"
                elif "deferred" in text_lower:
                    decision_type = "Deferred"

                link_tag = row.find("a", href=True)
                doc_url = None
                if link_tag:
                    href = link_tag["href"]
                    doc_url = href if href.startswith("http") else f"https://www.pbs.gov.au{href}"

                drug_name = self._match_drug_name(text, drug_names) or text[:80]
                decision_id = f"pbac-{hashlib.md5(text[:120].encode()).hexdigest()[:12]}"

                records.append({
                    "decision_id": decision_id,
                    "agency": "pbac",
                    "drug_name": drug_name,
                    "indication": None,
                    "decision_type": decision_type,
                    "decision_date": date_str,
                    "document_url": doc_url,
                    "summary": text[:300],
                })

        except Exception as e:
            logger.warning("PBAC scraping failed: %s", e)

        logger.info("Fetched %d PBAC decisions", len(records))
        return records

    # ------------------------------------------------------------------
    # Shared helpers for agency scrapers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_date_from_text(text: str) -> Optional[str]:
        """Try to extract a YYYY-MM-DD date from free text."""
        # ISO dates
        m = re.search(r'(\d{4}-\d{2}-\d{2})', text)
        if m:
            return m.group(1)
        # DD/MM/YYYY or DD.MM.YYYY
        m = re.search(r'(\d{1,2})[./](\d{1,2})[./](\d{4})', text)
        if m:
            day, month, year = m.group(1), m.group(2), m.group(3)
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        return None

    @staticmethod
    def _match_drug_name(text: str, drug_names: List[str]) -> Optional[str]:
        """Return the first drug name found in text, preserving original casing."""
        text_lower = text.lower()
        for name in drug_names:
            if name.lower() in text_lower:
                return name
        return None
