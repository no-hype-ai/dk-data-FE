"""Stabilis (IV Drug Compatibility) Fetcher.

Web-scrapes the Stabilis 4.0 database for intravenous drug compatibility
data. The site uses PHP endpoints:
- Molecule list: /Monographie.php?Liste
- Compatibility search: /RechercheIncompatibilites.php
- Individual monograph: /Monographie.php?IdMolecule=<N>

Source: https://www.stabilis.org
"""

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSStabilisFetcher(BaseFetcher):
    """Fetcher for IV drug compatibility data from Stabilis 4.0."""

    SOURCE_NAME = "cms_stabilis"
    BASE_URL = "https://www.stabilis.org"

    def get_latest_url(self) -> str:
        """Return the Stabilis molecule list URL."""
        return f"{self.BASE_URL}/Monographie.php?Liste"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Scrape IV compatibility data from Stabilis.

        Keyword Args:
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records", 5000)

        try:
            logger.info("Scraping IV compatibility data from %s", self.BASE_URL)

            # Step 1: Get molecule IDs from the main page
            molecule_ids = self._fetch_molecule_ids()
            logger.info("Found %d molecules on Stabilis", len(molecule_ids))

            if not molecule_ids:
                logger.warning("No molecule IDs found on Stabilis homepage")
                result: Dict[str, Any] = {
                    "status": "success",
                    "records": [],
                    "hash": None,
                }
                self.log_fetch_result(result)
                return result

            # Step 2: For each molecule, scrape its compatibility data
            records: List[Dict[str, Any]] = []
            seen_pairs: set = set()

            for mol_id, mol_name in molecule_ids:
                if max_records and len(records) >= max_records:
                    break

                mol_records = self._fetch_molecule_compatibilities(mol_id, mol_name)
                for rec in mol_records:
                    pair_key = tuple(sorted([rec["drug_a"], rec["drug_b"]]))
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        records.append(rec)

                    if max_records and len(records) >= max_records:
                        break

            records = records[:max_records] if max_records else records

            content_hash = hashlib.md5(
                str(len(records)).encode()
            ).hexdigest() if records else None

            result = {
                "status": "success",
                "records": records,
                "hash": content_hash,
            }
            self.log_fetch_result(result)
            return result

        except Exception as exc:
            logger.exception("Stabilis fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_molecule_ids(self) -> List[tuple]:
        """Scrape molecule IDs and names from the Stabilis homepage.

        Returns list of (id, name) tuples.
        """
        molecules = []

        # The homepage lists recent molecules with IdMolecule links
        try:
            resp = self.session.get(f"{self.BASE_URL}/index.php", timeout=60)
            resp.raise_for_status()
            html = resp.text

            # Extract molecule IDs from links like Monographie.php?IdMolecule=1275
            pattern = re.compile(
                r'Monographie\.php\?IdMolecule=(\d+)["\x27][^>]*>([^<]+)',
            )
            for match in pattern.finditer(html):
                mol_id = int(match.group(1))
                mol_name = match.group(2).strip()
                if mol_name:
                    molecules.append((mol_id, mol_name))

            # Also try the full molecule list page
            if len(molecules) < 50:
                resp2 = self.session.get(
                    f"{self.BASE_URL}/Monographie.php?Liste", timeout=60
                )
                resp2.raise_for_status()
                for match in pattern.finditer(resp2.text):
                    mol_id = int(match.group(1))
                    mol_name = match.group(2).strip()
                    if mol_name and (mol_id, mol_name) not in molecules:
                        molecules.append((mol_id, mol_name))

        except Exception as exc:
            logger.warning("Failed to fetch Stabilis molecule list: %s", exc)

        return molecules

    def _fetch_molecule_compatibilities(
        self, mol_id: int, mol_name: str
    ) -> List[Dict[str, Any]]:
        """Scrape compatibility data for a single molecule."""
        records = []

        try:
            url = f"{self.BASE_URL}/Monographie.php?IdMolecule={mol_id}"
            resp = self.session.get(url, timeout=60)
            resp.raise_for_status()

            records = self._parse_monograph_html(resp.text, mol_name)

        except Exception as exc:
            logger.debug("Stabilis monograph %s failed: %s", mol_name, exc)

        return records

    @staticmethod
    def _parse_monograph_html(
        html: str, drug_a: str
    ) -> List[Dict[str, Any]]:
        """Parse compatibility data from a molecule monograph page."""
        records = []

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.debug("BeautifulSoup not available for Stabilis parsing")
            return records

        soup = BeautifulSoup(html, "html.parser")

        # Look for compatibility tables — Stabilis uses tables with
        # columns for drug name, compatibility result, solvent, etc.
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    drug_b = cells[0].get_text(strip=True)
                    compatibility = cells[1].get_text(strip=True) if len(cells) > 1 else None
                    solvent = cells[2].get_text(strip=True) if len(cells) > 2 else None
                    concentration = cells[3].get_text(strip=True) if len(cells) > 3 else None
                    reference = cells[4].get_text(strip=True) if len(cells) > 4 else None

                    if drug_b and drug_b != drug_a:
                        records.append({
                            "drug_a": drug_a,
                            "drug_b": drug_b,
                            "compatibility": compatibility,
                            "solvent": solvent or None,
                            "concentration": concentration or None,
                            "reference": reference or None,
                        })

        return records
