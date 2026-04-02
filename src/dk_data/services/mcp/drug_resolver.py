"""Drug resolution middleware for MCP data tools.

Feature: 019-cms-puf-platform-reconciliation

Resolves a raw drug name query into canonical name, brand names, synonyms,
manufacturers, and SEC company names by querying:
  1. Local DB (mol_silver.molecules + mol_silver.molecule_aliases)
  2. FDA OpenFDA drug labels API
  3. ChEMBL molecule API
  4. PubChem compound API
  5. Fallback (identity)

All network calls use a 10-second timeout to avoid blocking the request path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Legal suffix patterns to strip for cleaner EDGAR entity matching
# ---------------------------------------------------------------------------

_LEGAL_SUFFIX_RE = re.compile(
    r"\b("
    r"Inc\.?|LLC\.?|Ltd\.?|Corp\.?|Co\.?|"
    r"Pharmaceuticals?|Biosciences?|Therapeutics?|"
    r"Holdings?|International|Laboratories?|Sciences?|"
    r"GmbH|AG|SE|S\.A\.|N\.V\.|PLC|"
    r"U\.S\.|US"
    r"),?",
    re.IGNORECASE,
)

# Known brand → clean entity substitutions
_BRAND_SUBSTITUTIONS: Dict[str, str] = {
    "sanofi-aventis": "sanofi",
    "sanofi aventis": "sanofi",
}


# ---------------------------------------------------------------------------
# DrugResolution dataclass
# ---------------------------------------------------------------------------


@dataclass
class DrugResolution:
    """Resolved drug identity with all known name forms and metadata."""

    query_name: str
    canonical_name: str
    brand_names: List[str] = field(default_factory=list)
    synonyms: List[str] = field(default_factory=list)
    manufacturers: List[str] = field(default_factory=list)
    sec_company_names: List[str] = field(default_factory=list)
    pubchem_cid: Optional[str] = None
    chembl_id: Optional[str] = None
    approved: bool = False
    clinical_stage: bool = False
    resolution_source: str = "fallback"
    from_cache: bool = False

    def all_names(self) -> List[str]:
        """Return all known name forms, deduplicated, canonical first."""
        seen: set[str] = set()
        result: List[str] = []
        for name in [self.canonical_name] + self.brand_names + self.synonyms:
            key = name.lower().strip()
            if key and key not in seen:
                seen.add(key)
                result.append(name)
        return result

    def faers_search_terms(self) -> List[str]:
        """Generic/substance names first, then brand names — for FAERS field queries."""
        seen: set[str] = set()
        result: List[str] = []
        # canonical (generic) first
        for name in [self.canonical_name] + self.synonyms:
            key = name.lower().strip()
            if key and key not in seen:
                seen.add(key)
                result.append(name)
        # brand names after
        for name in self.brand_names:
            key = name.lower().strip()
            if key and key not in seen:
                seen.add(key)
                result.append(name)
        return result

    def pubmed_query(self) -> str:
        """Return an OR-joined PubMed title/abstract query string."""
        terms = self.all_names()
        if not terms:
            return self.query_name
        quoted = [f'"{t}"' for t in terms]
        return " OR ".join(quoted)

    def edgar_search_terms(self) -> List[str]:
        """Return cleaned company/manufacturer names for EDGAR entity search."""
        return _clean_company_names(self.sec_company_names or self.manufacturers)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_company_names(names: List[str]) -> List[str]:
    """Strip legal suffixes and apply known substitutions for EDGAR matching."""
    cleaned: List[str] = []
    seen: set[str] = set()
    for raw in names:
        name = raw.strip()
        # Apply known substitutions first
        lower = name.lower()
        for pattern, replacement in _BRAND_SUBSTITUTIONS.items():
            if pattern in lower:
                name = replacement
                break
        else:
            # Strip trailing legal suffixes
            name = _LEGAL_SUFFIX_RE.sub("", name).strip().strip(",").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            cleaned.append(name)
        # Also keep original if it differs meaningfully
        if raw.strip() and raw.strip().lower() not in seen:
            seen.add(raw.strip().lower())
            cleaned.append(raw.strip())
    return cleaned


def _dedup(lst: List[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for item in lst:
        key = item.lower().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


# ---------------------------------------------------------------------------
# DrugResolver
# ---------------------------------------------------------------------------


class DrugResolver:
    """Resolve a drug name to its canonical form and all known aliases.

    Resolution chain (first success wins):
      1. Local DB — mol_silver.molecules / mol_silver.molecule_aliases
      2. FDA OpenFDA drug/label API
      3. ChEMBL molecule API
      4. PubChem compound API
      5. Identity fallback
    """

    OPENFDA_LABEL_URL = "https://api.fda.gov/drug/label.json"
    CHEMBL_MOLECULE_URL = "https://www.ebi.ac.uk/chembl/api/data/molecule.json"
    PUBCHEM_NAME_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/JSON"
    PUBCHEM_CID_SYNONYMS_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/synonyms/JSON"
    EDGAR_ENTITY_URL = "https://efts.sec.gov/LATEST/search-index"

    _HEADERS = {
        "User-Agent": "dk-data-platform research@dk-data.com",
        "Accept": "application/json",
    }

    async def resolve(self, drug_name: str, db_pool=None) -> DrugResolution:
        """Resolve drug_name through the full resolution chain."""
        name = drug_name.strip()
        if not name:
            return DrugResolution(
                query_name=drug_name,
                canonical_name=drug_name,
                resolution_source="fallback",
            )

        logger.debug("drug_resolver.resolve_start", drug_name=name)

        # 1. Local DB
        if db_pool is not None:
            try:
                result = await self._resolve_from_db(name, db_pool)
                if result is not None:
                    logger.info(
                        "drug_resolver.resolved",
                        drug_name=name,
                        source="local_db",
                        canonical=result.canonical_name,
                    )
                    return result
            except Exception as exc:
                logger.warning("drug_resolver.db_failed", drug_name=name, error=str(exc))

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=10.0,
            headers=self._HEADERS,
        ) as client:
            # 2. FDA OpenFDA labels
            try:
                result = await self._resolve_from_openfda(name, client)
                if result is not None:
                    logger.info(
                        "drug_resolver.resolved",
                        drug_name=name,
                        source="openfda_labels",
                        canonical=result.canonical_name,
                    )
                    return result
            except Exception as exc:
                logger.warning("drug_resolver.openfda_failed", drug_name=name, error=str(exc))

            # 3. ChEMBL
            try:
                result = await self._resolve_from_chembl(name, client)
                if result is not None:
                    logger.info(
                        "drug_resolver.resolved",
                        drug_name=name,
                        source="chembl",
                        canonical=result.canonical_name,
                    )
                    return result
            except Exception as exc:
                logger.warning("drug_resolver.chembl_failed", drug_name=name, error=str(exc))

            # 4. PubChem
            try:
                result = await self._resolve_from_pubchem(name, client)
                if result is not None:
                    logger.info(
                        "drug_resolver.resolved",
                        drug_name=name,
                        source="pubchem",
                        canonical=result.canonical_name,
                    )
                    return result
            except Exception as exc:
                logger.warning("drug_resolver.pubchem_failed", drug_name=name, error=str(exc))

        # 5. Fallback
        logger.info("drug_resolver.fallback", drug_name=name)
        return DrugResolution(
            query_name=name,
            canonical_name=name,
            resolution_source="fallback",
        )

    # ------------------------------------------------------------------ #
    # Resolution step 1: Local DB                                          #
    # ------------------------------------------------------------------ #

    async def _resolve_from_db(self, name: str, db_pool) -> Optional[DrugResolution]:
        normalized = name.lower().strip()
        async with db_pool.acquire() as conn:
            # Try canonical_name match first
            row = await conn.fetchrow(
                """
                SELECT id, canonical_name, brand_name, manufacturer,
                       pubchem_cid, chembl_id, drugbank_id
                FROM mol_silver.molecules
                WHERE LOWER(canonical_name) = $1
                LIMIT 1
                """,
                normalized,
            )
            if row is None:
                # Try alias lookup
                alias_row = await conn.fetchrow(
                    """
                    SELECT ma.molecule_id
                    FROM mol_silver.molecule_aliases ma
                    WHERE ma.alias_name_normalized = $1
                    LIMIT 1
                    """,
                    normalized,
                )
                if alias_row is not None:
                    row = await conn.fetchrow(
                        """
                        SELECT id, canonical_name, brand_name, manufacturer,
                               pubchem_cid, chembl_id, drugbank_id
                        FROM mol_silver.molecules
                        WHERE id = $1
                        LIMIT 1
                        """,
                        alias_row["molecule_id"],
                    )

        if row is None:
            return None

        brand_names = [row["brand_name"]] if row["brand_name"] else []
        manufacturers = [row["manufacturer"]] if row["manufacturer"] else []

        return DrugResolution(
            query_name=name,
            canonical_name=row["canonical_name"],
            brand_names=brand_names,
            synonyms=[],
            manufacturers=manufacturers,
            sec_company_names=_clean_company_names(manufacturers),
            pubchem_cid=row["pubchem_cid"],
            chembl_id=row["chembl_id"],
            approved=True,
            clinical_stage=True,
            resolution_source="local_db",
        )

    # ------------------------------------------------------------------ #
    # Resolution step 2: FDA OpenFDA drug labels                           #
    # ------------------------------------------------------------------ #

    async def _resolve_from_openfda(
        self, name: str, client: httpx.AsyncClient
    ) -> Optional[DrugResolution]:
        encoded = quote(name)
        # Try three field searches in order of specificity
        search_attempts = [
            f'openfda.generic_name:"{encoded}"',
            f'openfda.substance_name:"{encoded}"',
            f'openfda.brand_name:"{encoded}"',
        ]

        data: Optional[Dict[str, Any]] = None
        for search_expr in search_attempts:
            url = f"{self.OPENFDA_LABEL_URL}?search={search_expr}&limit=1"
            try:
                resp = await client.get(url)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                ct = resp.headers.get("content-type", "")
                if "json" not in ct:
                    continue
                payload = resp.json()
                results = payload.get("results", [])
                if results:
                    data = results[0]
                    break
            except httpx.HTTPStatusError:
                continue

        if data is None:
            return None

        openfda = data.get("openfda", {})
        generic_names: List[str] = openfda.get("generic_name", [])
        brand_names: List[str] = openfda.get("brand_name", [])
        substance_names: List[str] = openfda.get("substance_name", [])
        manufacturer_names: List[str] = openfda.get("manufacturer_name", [])

        canonical = generic_names[0] if generic_names else (substance_names[0] if substance_names else name)

        # Synonyms = substance names + generic names that aren't canonical
        synonyms = _dedup(substance_names + [g for g in generic_names if g != canonical])

        return DrugResolution(
            query_name=name,
            canonical_name=canonical,
            brand_names=_dedup(brand_names),
            synonyms=synonyms,
            manufacturers=_dedup(manufacturer_names),
            sec_company_names=_clean_company_names(manufacturer_names),
            approved=True,
            resolution_source="openfda_labels",
        )

    # ------------------------------------------------------------------ #
    # Resolution step 3: ChEMBL                                            #
    # ------------------------------------------------------------------ #

    async def _resolve_from_chembl(
        self, name: str, client: httpx.AsyncClient
    ) -> Optional[DrugResolution]:
        url = f"{self.CHEMBL_MOLECULE_URL}?q={quote(name)}&format=json&limit=1"
        resp = await client.get(url)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        if "json" not in ct:
            return None

        payload = resp.json()
        molecules = payload.get("molecules", [])
        if not molecules:
            return None

        mol = molecules[0]
        chembl_id: str = mol.get("molecule_chembl_id", "")
        pref_name: str = mol.get("pref_name") or name
        max_phase = mol.get("max_phase") or 0
        raw_synonyms: List[Dict[str, Any]] = mol.get("molecule_synonyms", [])
        synonyms = _dedup([
            s["molecule_synonym"]
            for s in raw_synonyms
            if s.get("molecule_synonym")
        ])

        return DrugResolution(
            query_name=name,
            canonical_name=pref_name,
            synonyms=synonyms,
            chembl_id=chembl_id,
            clinical_stage=max_phase is not None and max_phase > 0,
            approved=max_phase == 4,
            resolution_source="chembl",
        )

    # ------------------------------------------------------------------ #
    # Resolution step 4: PubChem                                           #
    # ------------------------------------------------------------------ #

    async def _resolve_from_pubchem(
        self, name: str, client: httpx.AsyncClient
    ) -> Optional[DrugResolution]:
        # Step A: get CID
        url_name = self.PUBCHEM_NAME_URL.format(name=quote(name))
        resp = await client.get(url_name)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        if "json" not in ct:
            return None

        payload = resp.json()
        pc_compounds = payload.get("PC_Compounds", [])
        if not pc_compounds:
            return None

        cid_val = pc_compounds[0].get("id", {}).get("id", {}).get("cid")
        if cid_val is None:
            return None
        cid_str = str(cid_val)

        # Step B: get synonyms for CID
        url_syn = self.PUBCHEM_CID_SYNONYMS_URL.format(cid=cid_str)
        try:
            resp2 = await client.get(url_syn)
            resp2.raise_for_status()
            ct2 = resp2.headers.get("content-type", "")
            if "json" not in ct2:
                synonyms: List[str] = []
            else:
                syn_payload = resp2.json()
                info_list = syn_payload.get("InformationList", {}).get("Information", [])
                synonyms = info_list[0].get("Synonym", []) if info_list else []
        except Exception:
            synonyms = []

        canonical = synonyms[0] if synonyms else name

        return DrugResolution(
            query_name=name,
            canonical_name=canonical,
            synonyms=_dedup(synonyms[1:20]),  # cap at 20 to avoid noise
            pubchem_cid=cid_str,
            resolution_source="pubchem",
        )

    # ------------------------------------------------------------------ #
    # EDGAR entity lookup (separate utility — not part of chain)           #
    # ------------------------------------------------------------------ #

    async def resolve_edgar_cik(
        self,
        company_names: List[str],
        timeout: float = 10.0,
    ) -> List[Dict[str, Any]]:
        """Search EDGAR for CIKs by company entity name.

        Uses the ?entity= parameter (not full-text ?q=) for precise entity
        matching. Returns list of {company_name, entity_name, cik} dicts.
        """
        results: List[Dict[str, Any]] = []
        cleaned = _clean_company_names(company_names)

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            headers=self._HEADERS,
        ) as client:
            for company in cleaned:
                url = (
                    f"{self.EDGAR_ENTITY_URL}"
                    f"?entity={quote(company)}"
                    f"&forms=10-K,10-Q,8-K"
                    f"&dateRange=custom&startdt=2020-01-01"
                )
                try:
                    resp = await client.get(url)
                    if resp.status_code == 404:
                        continue
                    resp.raise_for_status()
                    ct = resp.headers.get("content-type", "")
                    if "json" not in ct:
                        continue
                    data = resp.json()
                    hits = data.get("hits", {}).get("hits", [])
                    for hit in hits[:3]:
                        source = hit.get("_source", {})
                        entity_name = source.get("entity_name", "")
                        cik = source.get("file_date", "")  # EDGAR puts CIK in entity_id
                        # Try common field names for CIK
                        cik = (
                            source.get("cik")
                            or source.get("entity_id")
                            or hit.get("_id", "").split("/")[0]
                        )
                        results.append({
                            "company_name": company,
                            "entity_name": entity_name,
                            "cik": cik,
                        })
                        break  # one per company name is enough
                except Exception as exc:
                    logger.warning(
                        "drug_resolver.edgar_cik_failed",
                        company=company,
                        error=str(exc),
                    )
                    continue

        return results
