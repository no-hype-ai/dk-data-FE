"""HTA Bodies Decision Fetcher.

Feature: 011-datasource-integration
Task: T058-T060 — HTA Bodies CI source integration

Fetches technology appraisal decisions from Health Technology Assessment
(HTA) bodies.  Implements NICE (UK) via API, G-BA (Germany), HAS (France),
and PBAC (Australia) via web scraping.

Query-scoped from meta.ci_search_terms WHERE term_type = 'drug_name'.
Weekly cadence.

Sources:
- NICE: https://www.nice.org.uk/guidance/published?type=ta
- G-BA: https://www.g-ba.de/bewertungsverfahren/nutzenbewertung/
- HAS: https://www.has-sante.fr/
- PBAC: https://www.pbs.gov.au/pbs/industry/listing/elements/pbac-meetings
"""

import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# NICE search API for technology appraisals
# The old /api/guidance/published endpoint no longer exists (404).
# NICE uses a Next.js app with an internal search API.
NICE_API_BASE = "https://search-api.nice.org.uk/api/guidance/published"

# Agency identifiers
AGENCIES = ["nice", "gba", "has", "pbac"]


class HTABodiesFetcher(BaseFetcher):
    """Fetcher for HTA body decisions (multi-agency CI scope)."""

    SOURCE_NAME = "hta_bodies"
    BASE_URL = "https://www.nice.org.uk"

    def get_latest_url(self) -> str:
        """Return the NICE guidance API URL."""
        return NICE_API_BASE

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
                # Default fallback terms when meta.ci_search_terms is empty
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

            result: Dict[str, Any] = {
                "status": "success",
                "records": all_records,
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(all_records)})
            return result

        except Exception as e:
            logger.exception("HTA bodies fetch failed: %s", e)
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
        """Read drug names from meta.ci_search_terms.

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
                        FROM meta.ci_search_terms
                        WHERE term_type = 'drug_name'
                          AND is_active = TRUE
                        ORDER BY term_id
                        """
                    )
                    rows = cur.fetchall()

            names = [row[0] for row in rows]
            if names:
                logger.info(
                    "Loaded %d drug names from meta.ci_search_terms",
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

    def _fetch_nice(
        self,
        *,
        drug_names: List[str],
        days_back: int = 7,
    ) -> List[Dict[str, Any]]:
        """Fetch NICE technology appraisal decisions.

        Queries the NICE published guidance API for technology appraisals
        updated within the look-back window.

        Args:
            drug_names: Drug names to filter (post-fetch text match).
            days_back: Look-back window in days.

        Returns:
            List of normalized HTA decision dicts.
        """
        since_date = (
            datetime.now(timezone.utc) - timedelta(days=days_back)
        ).strftime("%Y-%m-%d")

        params = {
            "type": "ta",  # Technology Appraisals
            "from": since_date,
        }

        # Try the search API first, then fall back to the guidance page
        nice_endpoints = [
            NICE_API_BASE,
            "https://www.nice.org.uk/guidance/published",
        ]

        items: List[Dict] = []
        for endpoint in nice_endpoints:
            try:
                data = self.fetch_json(endpoint, params=params)
                items = self._extract_items(data)
                if items:
                    break
            except Exception as e:
                logger.debug("NICE endpoint %s failed: %s", endpoint, e)
                continue

        if not items:
            logger.info("No NICE guidance items returned from any endpoint")
            return []

        records: List[Dict[str, Any]] = []
        drug_names_lower = [d.lower() for d in drug_names] if drug_names else []

        for item in items:
            record = self._normalize_nice_item(item)
            if not record:
                continue

            # If drug_names are specified, filter by name match
            if drug_names_lower:
                item_drug = (record.get("drug_name") or "").lower()
                item_title = (record.get("summary") or "").lower()
                if not any(
                    dn in item_drug or dn in item_title
                    for dn in drug_names_lower
                ):
                    continue

            records.append(record)

        logger.info("Fetched %d NICE TA decisions", len(records))
        return records

    @staticmethod
    def _extract_items(data: Any) -> List[Dict]:
        """Extract list of items from a NICE API response."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("results", "data", "items", "guidance"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        return []

    @staticmethod
    def _normalize_nice_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize a NICE guidance item to the raw.hta_decisions schema.

        Returns None if no usable decision ID can be extracted.
        """
        decision_id = (
            item.get("id")
            or item.get("guidance_id")
            or item.get("reference")
        )
        if not decision_id:
            return None

        decision_id = f"nice-{decision_id}"

        # Decision date
        decision_date = (
            item.get("decision_date")
            or item.get("last_modified")
            or item.get("published_date")
            or item.get("date")
        )
        if decision_date:
            decision_date = str(decision_date)[:10]

        return {
            "decision_id": decision_id,
            "agency": "nice",
            "drug_name": item.get("drug_name") or item.get("title"),
            "indication": item.get("indication") or item.get("therapeutic_area"),
            "decision_type": item.get("decision_type") or item.get("type"),
            "decision_date": decision_date,
            "document_url": item.get("url") or item.get("document_url"),
            "summary": item.get("summary") or item.get("description"),
        }

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
        import re
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
