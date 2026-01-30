"""
Identifier Resolver Service

Resolves molecule identifiers across data sources using InChI Key as the master identifier.
Implements source precedence: DrugBank > ChEMBL > PubChem > Others

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

import re
import hashlib
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class IdentifierType(Enum):
    """Supported identifier types with regex patterns for auto-detection."""
    # Structural identifiers
    INCHI_KEY = "inchi_key"
    INCHI = "inchi"
    SMILES = "smiles"

    # Database-specific identifiers (alphabetical)
    ATC_CODE = "atc_code"           # WHO ATC classification (e.g., N02BE01)
    BINDINGDB_ID = "bindingdb_id"   # BindingDB ID (e.g., BDBM50000001)
    CAS_NUMBER = "cas_number"       # CAS Registry Number (e.g., 50-78-2)
    CHEMBL_ID = "chembl_id"         # ChEMBL ID (e.g., CHEMBL25)
    DAILYMED_SET_ID = "dailymed_set_id"  # DailyMed SPL Set ID (UUID format)
    DRUGBANK_ID = "drugbank_id"     # DrugBank ID (e.g., DB00945)
    EMA_NUMBER = "ema_number"       # EMA product number
    KEGG_ID = "kegg_id"             # KEGG Drug ID (e.g., D00001)
    NCT_ID = "nct_id"               # ClinicalTrials.gov ID (e.g., NCT00000001)
    NDC_CODE = "ndc_code"           # National Drug Code (e.g., 0069-2587-10)
    PDB_ID = "pdb_id"               # Protein Data Bank ID (e.g., 1ABC)
    PHARMGKB_ID = "pharmgkb_id"     # PharmGKB ID (e.g., PA449015)
    PUBCHEM_CID = "pubchem_cid"     # PubChem Compound ID (numeric)
    PUBCHEM_SID = "pubchem_sid"     # PubChem Substance ID (numeric)
    RESEARCH_CODE = "research_code" # Research/development code (e.g., CP-690,550)
    RXCUI = "rxcui"                 # RxNorm Concept Unique Identifier (numeric)
    STITCH_ID = "stitch_id"         # STITCH/SIDER ID (e.g., CIDs00000001)
    UNII = "unii"                   # FDA UNII code (e.g., R16CO5Y76E)
    UNIPROT_ID = "uniprot_id"       # UniProt accession (e.g., P00533)

    # Generic fallback
    NAME = "name"


# Regex patterns for identifier auto-detection (ordered from most specific to least)
IDENTIFIER_PATTERNS = {
    # Structural identifiers
    IdentifierType.INCHI_KEY: re.compile(r'^[A-Z]{14}-[A-Z]{10}-[A-Z]$'),
    IdentifierType.INCHI: re.compile(r'^InChI=1S?/'),

    # Database-specific identifiers (most specific patterns first)
    IdentifierType.NCT_ID: re.compile(r'^NCT\d{8}$', re.IGNORECASE),
    IdentifierType.CHEMBL_ID: re.compile(r'^CHEMBL\d+$', re.IGNORECASE),
    IdentifierType.DRUGBANK_ID: re.compile(r'^DB\d{5}$', re.IGNORECASE),
    IdentifierType.KEGG_ID: re.compile(r'^D\d{5}$'),  # KEGG Drug (D00001)
    IdentifierType.PHARMGKB_ID: re.compile(r'^PA\d+$', re.IGNORECASE),  # PA449015
    IdentifierType.BINDINGDB_ID: re.compile(r'^BDBM\d+$', re.IGNORECASE),  # BDBM50000001
    IdentifierType.ATC_CODE: re.compile(r'^[A-Z]\d{2}[A-Z]{2}\d{2}$'),  # N02BE01
    IdentifierType.CAS_NUMBER: re.compile(r'^\d{2,7}-\d{2}-\d$'),  # 50-78-2
    IdentifierType.NDC_CODE: re.compile(r'^\d{4,5}-\d{3,4}-\d{1,2}$'),  # 0069-2587-10
    IdentifierType.UNII: re.compile(r'^[A-Z0-9]{10}$'),  # 10 alphanumeric chars
    IdentifierType.STITCH_ID: re.compile(r'^CID[ms]?\d+$', re.IGNORECASE),  # CIDs00000001
    IdentifierType.EMA_NUMBER: re.compile(r'^EMEA/H/C/\d+$', re.IGNORECASE),
    IdentifierType.DAILYMED_SET_ID: re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE
    ),

    # Protein identifiers
    IdentifierType.UNIPROT_ID: re.compile(
        r'^[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}$'
    ),
    IdentifierType.PDB_ID: re.compile(r'^[0-9][A-Z0-9]{3}$', re.IGNORECASE),

    # Numeric identifiers (checked later due to ambiguity)
    # Note: RXCUI, PUBCHEM_CID, PUBCHEM_SID are all numeric - context determines type
    IdentifierType.RXCUI: re.compile(r'^\d{4,8}$'),  # Typically 4-8 digits
    IdentifierType.PUBCHEM_CID: re.compile(r'^\d+$'),  # Fallback for numeric

    # Research codes (varied formats like CP-690,550, PF-02341066, ABT-199)
    IdentifierType.RESEARCH_CODE: re.compile(r'^[A-Z]{2,4}[-\s]?\d{2,6}(,\d+)?$', re.IGNORECASE),

    # SMILES checked last (very permissive)
    IdentifierType.SMILES: re.compile(r'^[A-Za-z0-9@+\-\[\]()\\/#=%$]+$'),
}

# Source precedence for conflicting data (lower number = more trusted)
# Complete list of all 16+ data sources in the medallion architecture
SOURCE_PRECEDENCE = {
    # Tier 1: Curated authoritative sources
    'drugbank': 1,          # Highest quality curated drug data
    'chembl': 2,            # High quality bioactivity data

    # Tier 2: Regulatory/nomenclature sources
    'rxnorm': 3,            # FDA drug nomenclature standard
    'openfda_labels': 4,    # FDA approved drug labels
    'dailymed': 5,          # DailyMed drug labels
    'ema': 6,               # European Medicines Agency
    'who_inn': 7,           # WHO International Non-proprietary Names

    # Tier 3: Large compound databases
    'pubchem': 8,           # Large compound database
    'kegg_drug': 9,         # KEGG pathway/drug data

    # Tier 4: Specialized databases
    'pharmgkb': 10,         # Pharmacogenomics
    'openfda_faers': 11,    # FDA adverse events
    'sider': 12,            # Side effects database
    'bindingdb': 13,        # Binding affinity data
    'tdc_admet': 14,        # ADMET predictions

    # Tier 5: Clinical/publication sources
    'clinicaltrials': 15,   # ClinicalTrials.gov
    'clinicaltrials_gov': 15,  # Alias
    'openalex': 16,         # Publications
    'uniprot': 17,          # Protein targets

    # Tier 6: Supplementary sources
    'orange_book': 18,      # FDA Orange Book patents
    'uspto_patents': 19,    # Patent data
    'websearch': 20,        # Web search results
}

# Mapping from identifier type to preferred source for that identifier
IDENTIFIER_TO_SOURCE = {
    IdentifierType.DRUGBANK_ID: 'drugbank',
    IdentifierType.CHEMBL_ID: 'chembl',
    IdentifierType.RXCUI: 'rxnorm',
    IdentifierType.PUBCHEM_CID: 'pubchem',
    IdentifierType.PUBCHEM_SID: 'pubchem',
    IdentifierType.PHARMGKB_ID: 'pharmgkb',
    IdentifierType.KEGG_ID: 'kegg_drug',
    IdentifierType.ATC_CODE: 'who_inn',
    IdentifierType.UNIPROT_ID: 'uniprot',
    IdentifierType.NCT_ID: 'clinicaltrials',
    IdentifierType.NDC_CODE: 'dailymed',
    IdentifierType.UNII: 'openfda_labels',
    IdentifierType.CAS_NUMBER: 'pubchem',
    IdentifierType.PDB_ID: 'uniprot',
    IdentifierType.STITCH_ID: 'sider',
    IdentifierType.BINDINGDB_ID: 'bindingdb',
    IdentifierType.EMA_NUMBER: 'ema',
    IdentifierType.DAILYMED_SET_ID: 'dailymed',
    IdentifierType.RESEARCH_CODE: 'who_inn',
}


@dataclass
class ResolutionResult:
    """Result of identifier resolution."""
    molecule_id: Optional[str] = None
    inchi_key: Optional[str] = None
    canonical_name: Optional[str] = None
    confidence: float = 0.0
    match_type: str = "none"  # exact, structure, fuzzy, new
    needs_review: bool = False
    source: Optional[str] = None
    all_identifiers: Dict[str, str] = field(default_factory=dict)
    resolution_path: List[str] = field(default_factory=list)


class IdentifierResolver:
    """
    Resolves molecule identifiers across heterogeneous data sources.

    Resolution Strategy:
    1. Direct Lookup: Query identifier_mappings for exact match
    2. Structure-based: Convert SMILES → InChI Key using RDKit
    3. API Cross-reference: Query PubChem, ChEMBL, UniChem
    4. Fuzzy Name Matching: Use pg_trgm for name similarity
    5. Create New Entity: If no match found, create new molecule

    Quarantine: Records with confidence < 0.8 are marked needs_review=True
    """

    CONFIDENCE_THRESHOLD = 0.8  # Below this, records are quarantined

    def __init__(self, db_pool, fuzzy_matcher=None, external_apis=None):
        """
        Initialize the resolver.

        Args:
            db_pool: Database connection pool
            fuzzy_matcher: FuzzyMatcher instance for name matching
            external_apis: Dict of external API clients
        """
        self.db_pool = db_pool
        self.fuzzy_matcher = fuzzy_matcher
        self.external_apis = external_apis or {}
        self._rdkit_available = self._check_rdkit()

    def _check_rdkit(self) -> bool:
        """Check if RDKit is available for structure conversion."""
        try:
            from rdkit import Chem
            from rdkit.Chem.inchi import MolFromInchi, MolToInchi
            return True
        except ImportError:
            logger.warning("RDKit not available - structure-based resolution disabled")
            return False

    def detect_identifier_type(self, identifier: str) -> Optional[IdentifierType]:
        """
        Auto-detect identifier type using regex patterns.

        Args:
            identifier: The identifier string to analyze

        Returns:
            Detected IdentifierType or None if no pattern matches
        """
        identifier = identifier.strip()

        # Check specific patterns first (most restrictive to least)
        for id_type, pattern in IDENTIFIER_PATTERNS.items():
            if id_type == IdentifierType.SMILES:
                continue  # Check SMILES last as it's very permissive
            if pattern.match(identifier):
                return id_type

        # Check SMILES pattern last (very permissive)
        if IDENTIFIER_PATTERNS[IdentifierType.SMILES].match(identifier):
            # Additional validation: must have chemistry-like features
            if any(c in identifier for c in ['C', 'N', 'O', 'S', 'P', 'c', 'n', 'o']):
                return IdentifierType.SMILES

        # Default to NAME if nothing else matches
        return IdentifierType.NAME

    async def resolve(
        self,
        identifier: str,
        identifier_type: Optional[IdentifierType] = None,
        source: Optional[str] = None
    ) -> ResolutionResult:
        """
        Resolve an identifier to a canonical molecule.

        Args:
            identifier: The identifier to resolve
            identifier_type: Type of identifier (auto-detected if not provided)
            source: Source of the identifier (for provenance)

        Returns:
            ResolutionResult with molecule details and confidence
        """
        result = ResolutionResult(source=source)
        identifier = identifier.strip()

        # Auto-detect identifier type if not provided
        if identifier_type is None:
            identifier_type = self.detect_identifier_type(identifier)
            result.resolution_path.append(f"auto_detect:{identifier_type.value}")

        # Step 1: Direct lookup in identifier_mappings
        direct_result = await self._lookup_direct(identifier, identifier_type)
        if direct_result:
            result.molecule_id = direct_result['molecule_id']
            result.inchi_key = direct_result['inchi_key']
            result.canonical_name = direct_result['canonical_name']
            result.confidence = float(direct_result.get('confidence', 1.0))
            result.match_type = "exact"
            result.resolution_path.append("direct_lookup")
            return result

        # Step 2: Structure-based resolution (SMILES → InChI Key)
        if identifier_type == IdentifierType.SMILES and self._rdkit_available:
            inchi_key = self._smiles_to_inchi_key(identifier)
            if inchi_key:
                result.resolution_path.append("smiles_conversion")
                # Look up by generated InChI Key
                struct_result = await self._lookup_by_inchi_key(inchi_key)
                if struct_result:
                    result.molecule_id = struct_result['molecule_id']
                    result.inchi_key = inchi_key
                    result.canonical_name = struct_result['canonical_name']
                    result.confidence = 0.95  # High confidence for structure match
                    result.match_type = "structure"
                    return result
                else:
                    # New molecule with valid structure
                    result.inchi_key = inchi_key
                    result.confidence = 1.0
                    result.match_type = "new"
                    return result

        # Step 3: External API cross-reference
        if identifier_type in [IdentifierType.CHEMBL_ID, IdentifierType.DRUGBANK_ID,
                               IdentifierType.PUBCHEM_CID, IdentifierType.NAME]:
            api_result = await self._resolve_via_api(identifier, identifier_type)
            if api_result and api_result.get('inchi_key'):
                result.resolution_path.append("external_api")
                # Look up by API-provided InChI Key
                struct_result = await self._lookup_by_inchi_key(api_result['inchi_key'])
                if struct_result:
                    result.molecule_id = struct_result['molecule_id']
                    result.inchi_key = api_result['inchi_key']
                    result.canonical_name = struct_result['canonical_name']
                    result.confidence = 0.9
                    result.match_type = "api_crossref"
                    result.all_identifiers = api_result.get('identifiers', {})
                    return result
                else:
                    # New molecule from API
                    result.inchi_key = api_result['inchi_key']
                    result.canonical_name = api_result.get('name')
                    result.confidence = 0.9
                    result.match_type = "new"
                    result.all_identifiers = api_result.get('identifiers', {})
                    return result

        # Step 4: Fuzzy name matching (for NAME type)
        if identifier_type == IdentifierType.NAME and self.fuzzy_matcher:
            result.resolution_path.append("fuzzy_match")
            matches = await self.fuzzy_matcher.search(identifier, threshold=0.3, limit=5)
            if matches:
                best_match = matches[0]
                result.molecule_id = best_match['molecule_id']
                result.inchi_key = best_match['inchi_key']
                result.canonical_name = best_match['canonical_name']
                result.confidence = best_match['similarity']
                result.match_type = "fuzzy"

                # Quarantine if confidence below threshold
                if result.confidence < self.CONFIDENCE_THRESHOLD:
                    result.needs_review = True
                    result.resolution_path.append("quarantine")

                return result

        # Step 5: No match found - will create new entity
        result.match_type = "none"
        result.confidence = 0.0
        result.needs_review = True
        result.resolution_path.append("no_match")

        return result

    async def _lookup_direct(
        self,
        identifier: str,
        identifier_type: IdentifierType
    ) -> Optional[Dict[str, Any]]:
        """Look up identifier directly in identifier_mappings table."""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT
                    m.id AS molecule_id,
                    m.inchi_key,
                    m.canonical_name,
                    im.confidence
                FROM silver.identifier_mappings im
                JOIN silver.molecules m ON im.molecule_id = m.id
                WHERE im.identifier_value = $1
                  AND im.identifier_type = $2
                  AND m.needs_review = FALSE
                ORDER BY im.confidence DESC, im.is_primary DESC
                LIMIT 1
            """, identifier, identifier_type.value)

            if row:
                return dict(row)
            return None

    async def _lookup_by_inchi_key(self, inchi_key: str) -> Optional[Dict[str, Any]]:
        """Look up molecule by InChI Key."""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT
                    id AS molecule_id,
                    inchi_key,
                    canonical_name
                FROM silver.molecules
                WHERE inchi_key = $1
                  AND needs_review = FALSE
                LIMIT 1
            """, inchi_key)

            if row:
                return dict(row)
            return None

    def _smiles_to_inchi_key(self, smiles: str) -> Optional[str]:
        """Convert SMILES to InChI Key using RDKit."""
        if not self._rdkit_available:
            return None

        try:
            from rdkit import Chem
            from rdkit.Chem.inchi import MolToInchiKey

            mol = Chem.MolFromSmiles(smiles)
            if mol:
                return MolToInchiKey(mol)
        except Exception as e:
            logger.warning(f"SMILES to InChI Key conversion failed: {e}")

        return None

    async def _resolve_via_api(
        self,
        identifier: str,
        identifier_type: IdentifierType
    ) -> Optional[Dict[str, Any]]:
        """Resolve identifier via external API (PubChem, ChEMBL, etc.)."""
        # Implementation depends on external API clients
        # This is a placeholder for the actual API integration

        if 'pubchem' in self.external_apis and identifier_type in [
            IdentifierType.PUBCHEM_CID, IdentifierType.NAME
        ]:
            try:
                return await self.external_apis['pubchem'].resolve(identifier)
            except Exception as e:
                logger.warning(f"PubChem resolution failed: {e}")

        if 'chembl' in self.external_apis and identifier_type == IdentifierType.CHEMBL_ID:
            try:
                return await self.external_apis['chembl'].resolve(identifier)
            except Exception as e:
                logger.warning(f"ChEMBL resolution failed: {e}")

        return None

    def merge_molecule_data(
        self,
        records: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Merge molecule data from multiple sources using source precedence.

        DrugBank > ChEMBL > PubChem > Others

        Args:
            records: List of records from different sources

        Returns:
            Merged record with values from highest-precedence sources
        """
        if not records:
            return {}

        # Sort by source precedence (lower number = higher priority)
        sorted_records = sorted(
            records,
            key=lambda r: SOURCE_PRECEDENCE.get(r.get('source', ''), 999)
        )

        merged = {}
        sources_used = set()

        for record in sorted_records:
            source = record.get('source', 'unknown')
            for key, value in record.items():
                if key not in merged and value is not None:
                    merged[key] = value
                    if key not in ['source']:
                        sources_used.add(source)

        merged['data_sources'] = list(sources_used)
        merged['primary_source'] = sorted_records[0].get('source') if sorted_records else None

        return merged

    @staticmethod
    def calculate_resolution_confidence(
        match_type: str,
        similarity_score: Optional[float] = None
    ) -> float:
        """
        Calculate confidence score based on resolution method.

        Args:
            match_type: Type of match (exact, structure, fuzzy, api_crossref)
            similarity_score: Optional similarity score from fuzzy matching

        Returns:
            Confidence score between 0 and 1
        """
        base_scores = {
            'exact': 1.0,
            'structure': 0.95,
            'api_crossref': 0.9,
            'fuzzy': similarity_score or 0.5,
            'new': 1.0,
            'none': 0.0,
        }
        return base_scores.get(match_type, 0.5)
