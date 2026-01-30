"""
UMLS (Unified Medical Language System) API Client.

Provides access to UMLS terminology services for:
- Concept lookups (CUI)
- ICD-10 code mappings
- MeSH term resolution
- Semantic type queries
- Cross-vocabulary mappings

API Documentation: https://documentation.uts.nlm.nih.gov/rest/home.html
Rate Limit: 20 requests/second with API key
"""

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from loguru import logger

from .base_client import APIClientConfig, BaseAPIClient
from .cache_manager import CacheManager, DataSource


@dataclass
class UMLSConcept:
    """A UMLS Concept (CUI)."""

    cui: str  # Concept Unique Identifier
    name: str  # Preferred name
    semantic_types: List[str]  # Semantic type names
    semantic_type_ids: List[str]  # Semantic type TUIs
    atom_count: int = 0
    definition: Optional[str] = None
    sources: List[str] = None  # Source vocabularies

    def __post_init__(self):
        if self.sources is None:
            self.sources = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cui": self.cui,
            "name": self.name,
            "semantic_types": self.semantic_types,
            "semantic_type_ids": self.semantic_type_ids,
            "atom_count": self.atom_count,
            "definition": self.definition,
            "sources": self.sources,
        }


@dataclass
class UMLSAtom:
    """A UMLS Atom (specific term in a source vocabulary)."""

    aui: str  # Atom Unique Identifier
    cui: str  # Parent CUI
    name: str
    source: str  # Source vocabulary (e.g., "ICD10CM", "SNOMEDCT_US")
    source_code: str  # Code in source vocabulary
    term_type: str  # Term type (e.g., "PT" for preferred term)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "aui": self.aui,
            "cui": self.cui,
            "name": self.name,
            "source": self.source,
            "source_code": self.source_code,
            "term_type": self.term_type,
        }


@dataclass
class CrosswalkMapping:
    """A mapping between vocabulary codes via UMLS."""

    source_vocab: str
    source_code: str
    target_vocab: str
    target_code: str
    target_name: str
    relationship: str  # e.g., "SY" (synonym), "RN" (narrower)
    cui: str  # Linking CUI

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_vocab": self.source_vocab,
            "source_code": self.source_code,
            "target_vocab": self.target_vocab,
            "target_code": self.target_code,
            "target_name": self.target_name,
            "relationship": self.relationship,
            "cui": self.cui,
        }


class UMLSClient(BaseAPIClient[Dict[str, Any]]):
    """
    Client for UMLS REST API.

    Requires a UMLS API key from https://uts.nlm.nih.gov/uts/
    Set via UMLS_API_KEY environment variable.

    Usage:
        client = UMLSClient()
        concept = await client.get_concept("C0003864")  # Arthritis
        icd10_codes = await client.get_icd10_codes("C0003864")
    """

    # Source vocabularies supported
    VOCAB_ICD10CM = "ICD10CM"
    VOCAB_ICD10PCS = "ICD10PCS"
    VOCAB_SNOMEDCT = "SNOMEDCT_US"
    VOCAB_MESH = "MSH"
    VOCAB_RXNORM = "RXNORM"
    VOCAB_NDFRT = "NDFRT"
    VOCAB_ATC = "ATC"

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        api_key = os.getenv("UMLS_API_KEY")
        if not api_key:
            logger.warning("UMLS_API_KEY not set - UMLS queries will fail")

        config = APIClientConfig(
            base_url="https://uts-ws.nlm.nih.gov/rest",
            timeout=30.0,
            max_retries=3,
            requests_per_second=20.0,  # UMLS rate limit
            cache_ttl=2592000,  # 30 days (UMLS updates monthly)
        )
        super().__init__(config, cache_manager)
        self._api_key = api_key

    def _add_api_key(self, params: Optional[Dict] = None) -> Dict:
        """Add API key to request parameters."""
        if params is None:
            params = {}
        params["apiKey"] = self._api_key
        return params

    async def health_check(self) -> bool:
        """Check if UMLS API is accessible."""
        try:
            # Try to fetch a known concept
            result = await self._get(
                "/content/current/CUI/C0000001",
                params=self._add_api_key(),
                use_cache=False
            )
            return "result" in result
        except Exception as e:
            logger.error(f"UMLS health check failed: {e}")
            return False

    async def get_concept(self, cui: str) -> Optional[UMLSConcept]:
        """
        Get a UMLS concept by CUI.

        Args:
            cui: Concept Unique Identifier (e.g., "C0003864")

        Returns:
            UMLSConcept or None if not found
        """
        try:
            result = await self._get(
                f"/content/current/CUI/{cui}",
                params=self._add_api_key()
            )

            if "result" not in result:
                return None

            data = result["result"]
            return UMLSConcept(
                cui=data.get("ui", cui),
                name=data.get("name", ""),
                semantic_types=[st.get("name", "") for st in data.get("semanticTypes", [])],
                semantic_type_ids=[st.get("uri", "").split("/")[-1] for st in data.get("semanticTypes", [])],
                atom_count=data.get("atomCount", 0),
            )
        except Exception as e:
            logger.error(f"Error fetching UMLS concept {cui}: {e}")
            return None

    async def search_concepts(
        self,
        query: str,
        search_type: str = "words",
        page_size: int = 25,
        sources: Optional[List[str]] = None
    ) -> List[UMLSConcept]:
        """
        Search for UMLS concepts.

        Args:
            query: Search term
            search_type: "exact", "words", "leftTruncation", "rightTruncation"
            page_size: Number of results (max 100)
            sources: Filter by source vocabularies

        Returns:
            List of matching concepts
        """
        params = self._add_api_key({
            "string": query,
            "searchType": search_type,
            "pageSize": min(page_size, 100),
            "returnIdType": "concept",
        })

        if sources:
            params["sabs"] = ",".join(sources)

        try:
            result = await self._get("/search/current", params=params)

            concepts = []
            for item in result.get("result", {}).get("results", []):
                concepts.append(UMLSConcept(
                    cui=item.get("ui", ""),
                    name=item.get("name", ""),
                    semantic_types=[],  # Not included in search results
                    semantic_type_ids=[],
                ))
            return concepts
        except Exception as e:
            logger.error(f"Error searching UMLS for '{query}': {e}")
            return []

    async def get_atoms(
        self,
        cui: str,
        source: Optional[str] = None,
        page_size: int = 100
    ) -> List[UMLSAtom]:
        """
        Get atoms (source vocabulary terms) for a concept.

        Args:
            cui: Concept Unique Identifier
            source: Filter by source vocabulary (e.g., "ICD10CM")
            page_size: Number of results

        Returns:
            List of atoms
        """
        params = self._add_api_key({
            "pageSize": min(page_size, 100),
        })

        if source:
            params["sabs"] = source

        try:
            result = await self._get(
                f"/content/current/CUI/{cui}/atoms",
                params=params
            )

            atoms = []
            for item in result.get("result", []):
                atoms.append(UMLSAtom(
                    aui=item.get("ui", ""),
                    cui=cui,
                    name=item.get("name", ""),
                    source=item.get("rootSource", ""),
                    source_code=item.get("code", "").split("/")[-1],
                    term_type=item.get("termType", ""),
                ))
            return atoms
        except Exception as e:
            logger.error(f"Error fetching atoms for {cui}: {e}")
            return []

    async def get_icd10_codes(self, cui: str) -> List[str]:
        """
        Get ICD-10-CM codes mapped to a UMLS concept.

        Args:
            cui: Concept Unique Identifier

        Returns:
            List of ICD-10-CM codes
        """
        atoms = await self.get_atoms(cui, source=self.VOCAB_ICD10CM)
        return list(set(atom.source_code for atom in atoms if atom.source_code))

    async def get_mesh_terms(self, cui: str) -> List[str]:
        """
        Get MeSH terms mapped to a UMLS concept.

        Args:
            cui: Concept Unique Identifier

        Returns:
            List of MeSH descriptor UIDs
        """
        atoms = await self.get_atoms(cui, source=self.VOCAB_MESH)
        return list(set(atom.source_code for atom in atoms if atom.source_code))

    async def get_snomed_codes(self, cui: str) -> List[str]:
        """
        Get SNOMED-CT codes mapped to a UMLS concept.

        Args:
            cui: Concept Unique Identifier

        Returns:
            List of SNOMED-CT concept IDs
        """
        atoms = await self.get_atoms(cui, source=self.VOCAB_SNOMEDCT)
        return list(set(atom.source_code for atom in atoms if atom.source_code))

    async def crosswalk(
        self,
        source_vocab: str,
        source_code: str,
        target_vocab: str
    ) -> List[CrosswalkMapping]:
        """
        Map a code from one vocabulary to another via UMLS.

        Args:
            source_vocab: Source vocabulary (e.g., "ICD10CM")
            source_code: Code in source vocabulary
            target_vocab: Target vocabulary (e.g., "SNOMEDCT_US")

        Returns:
            List of crosswalk mappings
        """
        # First, find the CUI for the source code
        params = self._add_api_key({
            "string": source_code,
            "searchType": "exact",
            "sabs": source_vocab,
            "returnIdType": "concept",
        })

        try:
            result = await self._get("/search/current", params=params)
            search_results = result.get("result", {}).get("results", [])

            if not search_results:
                return []

            mappings = []
            for search_result in search_results[:5]:  # Limit to first 5 CUIs
                cui = search_result.get("ui", "")
                if not cui:
                    continue

                # Get atoms in target vocabulary
                atoms = await self.get_atoms(cui, source=target_vocab)

                for atom in atoms:
                    mappings.append(CrosswalkMapping(
                        source_vocab=source_vocab,
                        source_code=source_code,
                        target_vocab=target_vocab,
                        target_code=atom.source_code,
                        target_name=atom.name,
                        relationship="SY",  # Synonym relationship
                        cui=cui,
                    ))

            return mappings
        except Exception as e:
            logger.error(f"Error crosswalking {source_vocab}:{source_code} to {target_vocab}: {e}")
            return []

    async def icd10_to_snomed(self, icd10_code: str) -> List[str]:
        """
        Map ICD-10-CM code to SNOMED-CT codes.

        Args:
            icd10_code: ICD-10-CM code

        Returns:
            List of SNOMED-CT concept IDs
        """
        mappings = await self.crosswalk(
            self.VOCAB_ICD10CM,
            icd10_code,
            self.VOCAB_SNOMEDCT
        )
        return list(set(m.target_code for m in mappings))

    async def icd10_to_mesh(self, icd10_code: str) -> List[str]:
        """
        Map ICD-10-CM code to MeSH terms.

        Args:
            icd10_code: ICD-10-CM code

        Returns:
            List of MeSH descriptor UIDs
        """
        mappings = await self.crosswalk(
            self.VOCAB_ICD10CM,
            icd10_code,
            self.VOCAB_MESH
        )
        return list(set(m.target_code for m in mappings))

    async def get_related_concepts(
        self,
        cui: str,
        relation_type: Optional[str] = None,
        page_size: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get concepts related to a given concept.

        Args:
            cui: Concept Unique Identifier
            relation_type: Filter by relation (e.g., "RN" narrower, "RB" broader)
            page_size: Number of results

        Returns:
            List of related concept info dicts
        """
        params = self._add_api_key({"pageSize": min(page_size, 100)})

        try:
            result = await self._get(
                f"/content/current/CUI/{cui}/relations",
                params=params
            )

            relations = []
            for item in result.get("result", []):
                rel = item.get("relationLabel", "")
                if relation_type and rel != relation_type:
                    continue

                relations.append({
                    "cui": item.get("relatedId", "").split("/")[-1],
                    "name": item.get("relatedIdName", ""),
                    "relation": rel,
                    "additional_label": item.get("additionalRelationLabel", ""),
                })

            return relations
        except Exception as e:
            logger.error(f"Error fetching relations for {cui}: {e}")
            return []

    async def get_children(self, cui: str) -> List[Dict[str, Any]]:
        """Get narrower (child) concepts."""
        return await self.get_related_concepts(cui, relation_type="RN")

    async def get_parents(self, cui: str) -> List[Dict[str, Any]]:
        """Get broader (parent) concepts."""
        return await self.get_related_concepts(cui, relation_type="RB")

    async def get_definition(self, cui: str) -> Optional[str]:
        """
        Get the definition for a concept.

        Args:
            cui: Concept Unique Identifier

        Returns:
            Definition text or None
        """
        params = self._add_api_key()

        try:
            result = await self._get(
                f"/content/current/CUI/{cui}/definitions",
                params=params
            )

            definitions = result.get("result", [])
            if definitions:
                # Prefer NCI or MSH definitions
                for defn in definitions:
                    source = defn.get("rootSource", "")
                    if source in ["NCI", "MSH"]:
                        return defn.get("value", "")
                # Fall back to first definition
                return definitions[0].get("value", "")
            return None
        except Exception as e:
            logger.error(f"Error fetching definition for {cui}: {e}")
            return None


# Singleton instance
_umls_client: Optional[UMLSClient] = None


async def get_umls_client(cache_manager: Optional[CacheManager] = None) -> UMLSClient:
    """Get or create the UMLS client instance."""
    global _umls_client

    if _umls_client is None:
        _umls_client = UMLSClient(cache_manager)

    return _umls_client
