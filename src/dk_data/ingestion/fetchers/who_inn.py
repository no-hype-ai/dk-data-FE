"""WHO INN (International Nonproprietary Names) Fetcher.

Feature: 019-cms-puf-platform-reconciliation

Fetches WHO International Nonproprietary Names via the PubChem Synonyms API.
No credentials required — PubChem is an open public API.

PubChem Synonyms endpoint:
  https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/synonyms/JSON

PubChem Compound Properties endpoint:
  https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/property/IUPACName,IsomericSMILES,InChIKey,MolecularFormula/JSON

Response format stored in mol_raw.who_inn:
  {"InformationList": {"Information": [{"CID": int, "Synonym": [...]}]}}

The bronze SQLMesh model (mol_bronze.who_inn) handles two formats:
  1. "direct format": response_body has inn_name, cas_number, inn_stem, etc. at top level
  2. "PubChem synonyms format": InformationList.Information[].{CID, Synonym:[...]}

Strategy: for each INN drug name in PHARMA_INN_SEEDS (or caller-supplied list),
call the PubChem synonyms endpoint and store the raw InformationList response.
A 0.2 s delay between requests respects PubChem's rate limits.
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# PubChem REST API base URL
PUBCHEM_BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

# PubChem endpoints
PUBCHEM_SYNONYMS_URL = (
    PUBCHEM_BASE_URL + "/compound/name/{name}/synonyms/JSON"
)
PUBCHEM_PROPERTIES_URL = (
    PUBCHEM_BASE_URL
    + "/compound/name/{name}/property/IUPACName,IsomericSMILES,InChIKey,MolecularFormula/JSON"
)

# Rate-limit courtesy delay between PubChem requests (seconds).
# Official PubChem PUG REST limit: 5 req/s, 400 req/min, 300s server compute/min.
# X-Throttling-Control response headers must be respected; violations result in IP bans.
# 0.21s keeps us just under 5 req/s ceiling with a small safety margin.
REQUEST_DELAY_SECONDS = 0.21

# Representative set of ~50 common WHO INNs used as default seed list.
# Covers small molecules, biologics, oncology, and common chronic-disease drugs.
PHARMA_INN_SEEDS: List[str] = [
    "ibuprofen",
    "atorvastatin",
    "lisinopril",
    "metformin",
    "omeprazole",
    "simvastatin",
    "amlodipine",
    "metoprolol",
    "losartan",
    "albuterol",
    "fluoxetine",
    "sertraline",
    "gabapentin",
    "pantoprazole",
    "montelukast",
    "rosuvastatin",
    "escitalopram",
    "duloxetine",
    "tramadol",
    "hydrocodone",
    "oxycodone",
    "alprazolam",
    "zolpidem",
    "cetirizine",
    "loratadine",
    "warfarin",
    "clopidogrel",
    "aspirin",
    "acetaminophen",
    "naproxen",
    "prednisone",
    "levothyroxine",
    "insulin",
    "sildenafil",
    "tadalafil",
    "vardenafil",
    "adalimumab",
    "etanercept",
    "infliximab",
    "rituximab",
    "bevacizumab",
    "trastuzumab",
    "pembrolizumab",
    "nivolumab",
    "ipilimumab",
    "sorafenib",
    "imatinib",
    "erlotinib",
    "gefitinib",
    "osimertinib",
]


class WHOINNFetcher(BaseFetcher):
    """Fetcher for WHO INN data via the PubChem Synonyms API.

    No credentials are required. For each INN name in the seed list (or a
    caller-supplied override list), the PubChem compound/name/{name}/synonyms
    endpoint is called and the raw InformationList response is stored verbatim
    as a record.
    """

    SOURCE_NAME = "who_inn"
    BASE_URL = PUBCHEM_BASE_URL

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)
        self.session.headers.update({
            "Accept": "application/json",
        })

    def get_latest_url(self) -> str:
        """Return the PubChem base URL (no single versioned endpoint exists)."""
        return PUBCHEM_BASE_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch PubChem synonym records for a list of WHO INN drug names.

        Keyword Args:
            drug_names: Optional list of INN names to query. Defaults to
                        PHARMA_INN_SEEDS when not supplied.

        Returns:
            Dict with keys:
                status        — "success" | "failed"
                records       — list of raw PubChem InformationList response dicts
                record_count  — number of records collected
                hash          — MD5 content hash over CIDs / names seen
                errors        — list of per-name error strings (up to 20)
        """
        drug_names: List[str] = kwargs.get("drug_names", PHARMA_INN_SEEDS)

        records: List[Dict[str, Any]] = []
        errors: List[str] = []

        try:
            for name in drug_names:
                try:
                    record = self._fetch_pubchem_synonyms(name)
                    if record is not None:
                        records.append(record)
                except Exception as exc:
                    msg = f"{name}: {exc}"
                    errors.append(msg)
                    logger.warning("PubChem synonyms fetch failed for %r: %s", name, exc)

                time.sleep(REQUEST_DELAY_SECONDS)

            # Content hash over the CIDs or names that were successfully retrieved
            cid_or_name_list = []
            for r in records:
                info_list = r.get("InformationList", {}).get("Information", [])
                for info in info_list:
                    cid_or_name_list.append(str(info.get("CID", "")))
            if not cid_or_name_list:
                cid_or_name_list = [str(n) for n in drug_names]

            content_hash = hashlib.md5(
                json.dumps(sorted(cid_or_name_list), sort_keys=True).encode()
            ).hexdigest()

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
                "errors": errors[:20],
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except Exception as e:
            logger.exception("WHO INN fetch failed: %s", e)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "errors": [str(e)],
            }
            self.log_fetch_result(result)
            return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_pubchem_synonyms(self, name: str) -> Optional[Dict[str, Any]]:
        """Fetch PubChem synonyms for a single compound name.

        Args:
            name: INN drug name (e.g. "ibuprofen").

        Returns:
            The raw PubChem InformationList response dict, or None if the
            compound was not found (404) or the response was malformed.
        """
        url = PUBCHEM_SYNONYMS_URL.format(name=name)
        try:
            response = self.session.get(url, timeout=30)
        except Exception as exc:
            raise RuntimeError(f"HTTP request failed: {exc}") from exc

        if response.status_code == 404:
            logger.debug("PubChem: compound %r not found (404)", name)
            return None

        # Respect PubChem throttle signal — back off if throttled
        throttle_header = response.headers.get("X-Throttling-Control", "")
        if throttle_header:
            # Format: "Request Count status: ..., Request Time status: ..."
            # If any status is "Yellow" back off 1s; "Red" back off 3s
            if "Red" in throttle_header:
                logger.warning("PubChem throttle Red — backing off 3s")
                time.sleep(3.0)
            elif "Yellow" in throttle_header:
                logger.debug("PubChem throttle Yellow — backing off 1s")
                time.sleep(1.0)

        response.raise_for_status()

        try:
            data = response.json()
        except Exception as exc:
            raise RuntimeError(f"JSON decode error: {exc}") from exc

        # Validate expected response shape
        if "InformationList" not in data:
            logger.warning(
                "PubChem synonyms response for %r missing InformationList key", name
            )
            return None

        # Attach the queried name for traceability in the loader
        data["_queried_name"] = name
        return data

    def _fetch_pubchem_properties(self, name: str) -> Optional[Dict[str, Any]]:
        """Fetch PubChem compound properties for a single name.

        This is a supplementary call; it is not invoked by default in fetch()
        but is available for callers who want richer property data alongside
        the synonyms.

        Args:
            name: INN drug name.

        Returns:
            PubChem PropertyTable response dict, or None on 404 / error.
        """
        url = PUBCHEM_PROPERTIES_URL.format(name=name)
        try:
            response = self.session.get(url, timeout=30)
        except Exception as exc:
            raise RuntimeError(f"HTTP request failed: {exc}") from exc

        if response.status_code == 404:
            logger.debug("PubChem properties: compound %r not found (404)", name)
            return None

        response.raise_for_status()

        try:
            return response.json()
        except Exception as exc:
            raise RuntimeError(f"JSON decode error: {exc}") from exc
