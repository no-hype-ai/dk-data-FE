"""
Indication Resolver Service.

Maps free-text indications to standardized ICD-10 codes using a 4-layer approach:
1. Local Ontology - Fast lookup in YAML-based local mappings
2. Authority Lookup - Direct lookup in UMLS/MeSH for exact matches
3. WHO ICD API - Dynamic lookup from official WHO ICD-10/ICD-11 database
4. ML Classification - LLM-based classification for ambiguous terms

Follows the classifier confidence thresholds from scoring_config.yaml.
Uses YAML-based ontology mappings loaded by OntologyLoader with WHO ICD API fallback.
"""

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml
from loguru import logger

from ...models.indication import (
    ICD10Code,
    ICD10Level,
    Indication,
    IndicationSource,
)
from ..external_apis import (
    UMLSClient,
    UMLSConcept,
    get_umls_client,
    WHOICDClient,
    ICDCode,
    get_who_icd_client,
)
from .ontology_loader import get_ontology_loader, OntologyLoader


@dataclass
class ResolverConfig:
    """Configuration for indication resolution."""

    # Confidence thresholds
    high_confidence: float = 0.90
    medium_confidence: float = 0.75
    low_confidence: float = 0.50
    reject_threshold: float = 0.30

    # Ontology boost when ML and ontology agree
    ontology_boost: float = 0.10

    # Authority lookup overrides ML
    authority_override: bool = True

    # Maximum results per layer
    max_results: int = 10


@dataclass
class ResolutionResult:
    """Result of indication resolution."""

    original_text: str
    resolved: bool = False

    # Best match
    icd10_code: Optional[str] = None
    icd10_description: Optional[str] = None
    confidence: float = 0.0

    # Resolution method
    method: str = "none"  # authority, ontology, ml, hybrid

    # All candidates
    candidates: List[Dict[str, Any]] = field(default_factory=list)

    # UMLS mapping
    umls_cui: Optional[str] = None
    umls_name: Optional[str] = None

    # Warnings/notes
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_text": self.original_text,
            "resolved": self.resolved,
            "icd10_code": self.icd10_code,
            "icd10_description": self.icd10_description,
            "confidence": self.confidence,
            "method": self.method,
            "candidates": self.candidates,
            "umls_cui": self.umls_cui,
            "umls_name": self.umls_name,
            "warnings": self.warnings,
        }


class IndicationResolver:
    """
    Resolves free-text indications to ICD-10 codes.

    Uses YAML-based ontology mappings for abbreviations and ICD-10 codes.
    All mappings are loaded from config/ontology_mappings.yaml.

    Usage:
        resolver = IndicationResolver()
        await resolver.initialize()

        result = await resolver.resolve("rheumatoid arthritis")
        print(result.icd10_code)  # "M05.79"
    """

    def __init__(
        self,
        config: Optional[ResolverConfig] = None,
        ontology_loader: Optional[OntologyLoader] = None,
    ):
        self.config = config or ResolverConfig()
        self._umls: Optional[UMLSClient] = None
        self._who_icd: Optional[WHOICDClient] = None
        self._icd10_cache: Dict[str, ICD10Code] = {}
        self._ontology = ontology_loader or get_ontology_loader()

    @property
    def NORMALIZATION_MAP(self) -> Dict[str, str]:
        """Get abbreviation mappings from ontology (for backwards compatibility)."""
        return self._ontology.mappings.abbreviations

    async def initialize(self) -> None:
        """Initialize the resolver."""
        self._umls = await get_umls_client()

        # Initialize WHO ICD client (optional - won't fail if credentials missing)
        try:
            self._who_icd = await get_who_icd_client()
            logger.info("WHO ICD API client initialized for dynamic resolution")
        except Exception as e:
            logger.debug(f"WHO ICD client not available: {e}")
            self._who_icd = None

        await self._load_config()

    async def _load_config(self) -> None:
        """Load configuration from YAML file."""
        try:
            config_path = os.path.join(
                os.path.dirname(__file__),
                "../../../config/scoring_config.yaml"
            )
            with open(config_path, "r") as f:
                yaml_config = yaml.safe_load(f)

            ml_config = yaml_config.get("ml_classifier", {}).get("intervention", {})
            self.config.high_confidence = ml_config.get("high_confidence", 0.90)
            self.config.medium_confidence = ml_config.get("medium_confidence", 0.75)
            self.config.low_confidence = ml_config.get("low_confidence", 0.50)
            self.config.reject_threshold = ml_config.get("reject_threshold", 0.30)
            self.config.authority_override = yaml_config.get("ml_classifier", {}).get("authority_override", True)
            self.config.ontology_boost = yaml_config.get("ml_classifier", {}).get("ontology_boost", 0.10)

            logger.info("Loaded resolver configuration")
        except Exception as e:
            logger.warning(f"Could not load resolver config: {e}, using defaults")

    def normalize_indication(self, text: str) -> str:
        """
        Normalize an indication string.

        - Lowercase
        - Expand common abbreviations (from YAML config)
        - Remove extra whitespace
        - Handle common variations
        """
        text = text.lower().strip()

        # Remove parenthetical notes
        text = re.sub(r'\([^)]*\)', '', text).strip()

        # Expand abbreviations using ontology loader
        text = self._ontology.expand_abbreviations(text)

        # Normalize whitespace
        text = ' '.join(text.split())

        return text

    async def resolve(
        self,
        indication_text: str,
        therapeutic_area: Optional[str] = None,
    ) -> ResolutionResult:
        """
        Resolve a free-text indication to ICD-10 code.

        Uses a 4-layer resolution strategy:
        1. Local Ontology - Fast lookup in YAML-based local mappings
        2. UMLS Authority - Direct lookup in UMLS for exact matches
        3. WHO ICD API - Dynamic lookup from official WHO ICD-10 database
        4. UMLS Ontology - Semantic matching using UMLS concept relationships

        Args:
            indication_text: Free-text indication
            therapeutic_area: Optional therapeutic area hint

        Returns:
            ResolutionResult with ICD-10 code and confidence
        """
        result = ResolutionResult(original_text=indication_text)

        # Normalize input
        normalized = self.normalize_indication(indication_text)

        # Layer 0: Local YAML Ontology (fastest)
        local_result = self._local_ontology_lookup(normalized)
        if local_result and local_result[1] >= self.config.high_confidence:
            result.resolved = True
            result.icd10_code = local_result[0].code
            result.icd10_description = local_result[0].description
            result.confidence = local_result[1]
            result.method = "local_ontology"
            return result

        # Layer 1: Authority Lookup (UMLS)
        authority_result = await self._authority_lookup(normalized)
        if authority_result and authority_result[1] >= self.config.high_confidence:
            result.resolved = True
            result.icd10_code = authority_result[0].code
            result.icd10_description = authority_result[0].description
            result.confidence = authority_result[1]
            result.method = "authority"
            result.umls_cui = authority_result[0].umls_cui
            return result

        # Layer 2: WHO ICD API (official WHO ICD-10 database)
        who_result = await self._who_icd_lookup(normalized, therapeutic_area)
        if who_result and who_result[1] >= self.config.medium_confidence:
            result.resolved = True
            result.icd10_code = who_result[0].code
            result.icd10_description = who_result[0].description
            result.confidence = who_result[1]
            result.method = "who_icd"
            result.candidates.append({
                "code": who_result[0].code,
                "description": who_result[0].description,
                "confidence": who_result[1],
                "method": "who_icd",
            })
            return result

        # Layer 3: Ontology Mapping (UMLS semantic matching)
        ontology_results = await self._ontology_mapping(normalized)
        if ontology_results:
            best_ontology = ontology_results[0]
            result.candidates.extend([
                {
                    "code": r[0].code,
                    "description": r[0].description,
                    "confidence": r[1],
                    "method": "ontology",
                }
                for r in ontology_results[:self.config.max_results]
            ])

            if best_ontology[1] >= self.config.medium_confidence:
                result.resolved = True
                result.icd10_code = best_ontology[0].code
                result.icd10_description = best_ontology[0].description
                result.confidence = best_ontology[1]
                result.method = "ontology"
                result.umls_cui = best_ontology[0].umls_cui
                return result

        # Layer 4: ML Classification (LLM-based, placeholder)
        ml_result = await self._ml_classification(normalized, therapeutic_area)
        if ml_result:
            result.candidates.append({
                "code": ml_result[0].code if ml_result[0] else None,
                "description": ml_result[0].description if ml_result[0] else None,
                "confidence": ml_result[1],
                "method": "ml",
            })

            # Check if ontology agrees with ML (boost confidence)
            if ontology_results and ml_result[0]:
                for ont_result in ontology_results:
                    if ont_result[0].code == ml_result[0].code:
                        ml_result = (ml_result[0], min(1.0, ml_result[1] + self.config.ontology_boost))
                        result.method = "hybrid"
                        break

            if ml_result[1] >= self.config.low_confidence:
                result.resolved = True
                result.icd10_code = ml_result[0].code if ml_result[0] else None
                result.icd10_description = ml_result[0].description if ml_result[0] else None
                result.confidence = ml_result[1]
                if result.method != "hybrid":
                    result.method = "ml"
                return result

        # Could not resolve with sufficient confidence
        if result.candidates:
            result.warnings.append("Low confidence resolution - manual review recommended")
            # Use best candidate anyway
            best = max(result.candidates, key=lambda c: c["confidence"])
            result.icd10_code = best["code"]
            result.icd10_description = best["description"]
            result.confidence = best["confidence"]
            result.method = best["method"]
        else:
            result.warnings.append("Could not resolve indication to ICD-10 code")

        return result

    def _local_ontology_lookup(
        self,
        normalized_text: str,
    ) -> Optional[Tuple[ICD10Code, float]]:
        """
        Layer 0: Fast lookup in local YAML-based ontology mappings.

        Returns (ICD10Code, confidence) or None.
        """
        try:
            icd10_result = self._ontology.get_icd10_code(normalized_text)

            if icd10_result:
                code, chapter = icd10_result
                icd10 = ICD10Code(
                    code=code,
                    description=normalized_text.title(),
                    level=ICD10Code.parse_code_level(code),
                )
                # High confidence for exact match in curated local ontology
                return (icd10, 0.95)

        except Exception as e:
            logger.debug(f"Local ontology lookup error for '{normalized_text}': {e}")

        return None

    async def _who_icd_lookup(
        self,
        normalized_text: str,
        therapeutic_area: Optional[str] = None,
    ) -> Optional[Tuple[ICD10Code, float]]:
        """
        Layer 2: WHO ICD API lookup for official ICD-10 codes.

        Returns (ICD10Code, confidence) or None.
        """
        if not self._who_icd:
            return None

        try:
            icd_code = await self._who_icd.lookup_icd10_by_indication(
                indication=normalized_text,
                therapeutic_area=therapeutic_area,
            )

            if icd_code:
                icd10 = ICD10Code(
                    code=icd_code.code,
                    description=icd_code.title,
                    level=ICD10Code.parse_code_level(icd_code.code),
                )
                # High confidence for WHO ICD API match
                return (icd10, 0.90)

        except Exception as e:
            logger.warning(f"WHO ICD lookup failed for '{normalized_text}': {e}")

        return None

    async def _authority_lookup(
        self,
        normalized_text: str,
    ) -> Optional[Tuple[ICD10Code, float]]:
        """
        Layer 1: Direct authority lookup in UMLS.

        Returns (ICD10Code, confidence) or None.
        """
        try:
            # Search UMLS for exact match
            concepts = await self._umls.search_concepts(
                query=normalized_text,
                search_type="exact",
                page_size=5,
                sources=["ICD10CM"],
            )

            if not concepts:
                # Try normalized search
                concepts = await self._umls.search_concepts(
                    query=normalized_text,
                    search_type="words",
                    page_size=10,
                    sources=["ICD10CM"],
                )

            for concept in concepts:
                # Get ICD-10 codes for this concept
                icd10_codes = await self._umls.get_icd10_codes(concept.cui)

                if icd10_codes:
                    # Use first (most specific) code
                    code = icd10_codes[0]
                    icd10 = ICD10Code(
                        code=code,
                        description=concept.name,
                        level=ICD10Code.parse_code_level(code),
                        umls_cui=concept.cui,
                    )

                    # High confidence for exact match
                    confidence = 0.95 if len(concepts) == 1 else 0.85

                    return (icd10, confidence)

        except Exception as e:
            logger.error(f"Authority lookup failed for '{normalized_text}': {e}")

        return None

    async def _ontology_mapping(
        self,
        normalized_text: str,
    ) -> List[Tuple[ICD10Code, float]]:
        """
        Layer 2: Ontology-based mapping using UMLS relationships.

        Returns list of (ICD10Code, confidence) sorted by confidence.
        """
        results = []

        try:
            # Search for related concepts
            concepts = await self._umls.search_concepts(
                query=normalized_text,
                search_type="words",
                page_size=20,
            )

            for concept in concepts:
                # Get ICD-10 codes via UMLS atoms
                icd10_codes = await self._umls.get_icd10_codes(concept.cui)

                for code in icd10_codes[:3]:  # Limit per concept
                    icd10 = ICD10Code(
                        code=code,
                        description=concept.name,
                        level=ICD10Code.parse_code_level(code),
                        umls_cui=concept.cui,
                    )

                    # Calculate confidence based on match quality
                    name_match = self._calculate_text_similarity(
                        normalized_text,
                        concept.name.lower()
                    )
                    confidence = 0.5 + (0.4 * name_match)

                    results.append((icd10, confidence))

            # Sort by confidence and deduplicate
            results.sort(key=lambda x: x[1], reverse=True)
            seen_codes: Set[str] = set()
            unique_results = []
            for icd10, conf in results:
                if icd10.code not in seen_codes:
                    seen_codes.add(icd10.code)
                    unique_results.append((icd10, conf))

            return unique_results[:self.config.max_results]

        except Exception as e:
            logger.error(f"Ontology mapping failed for '{normalized_text}': {e}")

        return results

    async def _ml_classification(
        self,
        normalized_text: str,
        therapeutic_area: Optional[str] = None,
    ) -> Optional[Tuple[Optional[ICD10Code], float]]:
        """
        Layer 3: ML-based classification.

        This is a placeholder for LLM integration (GPT-5-nano or self-hosted).
        Currently returns a heuristic-based result.

        In production, this would call the Analysis Agent's LLM endpoint.
        """
        # Placeholder: In production, this would use the LLM
        # For now, return None to fall back to ontology results
        logger.debug(f"ML classification placeholder for '{normalized_text}'")

        # Could implement simple heuristics here as fallback
        # or call an LLM API

        return None

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate simple text similarity score.

        Uses word overlap (Jaccard-like).
        """
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union)

    async def resolve_batch(
        self,
        indications: List[str],
        therapeutic_area: Optional[str] = None,
    ) -> List[ResolutionResult]:
        """
        Resolve multiple indications.

        Args:
            indications: List of indication texts
            therapeutic_area: Optional therapeutic area hint

        Returns:
            List of ResolutionResults
        """
        results = []
        for indication in indications:
            result = await self.resolve(indication, therapeutic_area)
            results.append(result)
        return results

    async def expand_icd10_hierarchy(
        self,
        icd10_code: str,
        include_parents: bool = True,
        include_children: bool = True,
        include_siblings: bool = False,
    ) -> List[str]:
        """
        Expand an ICD-10 code to related codes in the hierarchy.

        Args:
            icd10_code: The base ICD-10 code
            include_parents: Include parent codes
            include_children: Include child codes
            include_siblings: Include sibling codes

        Returns:
            List of related ICD-10 codes
        """
        related_codes = [icd10_code]

        # Parse the code structure
        code_len = len(icd10_code.replace(".", ""))

        if include_parents:
            # Get parent codes by truncating
            current = icd10_code
            while len(current) > 1:
                if "." in current:
                    # Remove last character after decimal
                    parts = current.split(".")
                    if len(parts[1]) > 0:
                        parts[1] = parts[1][:-1]
                        if parts[1]:
                            current = ".".join(parts)
                        else:
                            current = parts[0]
                    else:
                        current = parts[0]
                else:
                    # Remove last character
                    current = current[:-1]

                if current and current not in related_codes:
                    related_codes.append(current)

        # For children and siblings, we would need to query UMLS
        # This is a simplified implementation
        if include_children or include_siblings:
            try:
                # Search for codes starting with this prefix
                concepts = await self._umls.search_concepts(
                    query=icd10_code,
                    search_type="leftTruncation",
                    page_size=50,
                    sources=["ICD10CM"],
                )

                for concept in concepts:
                    codes = await self._umls.get_icd10_codes(concept.cui)
                    for code in codes:
                        if include_children and code.startswith(icd10_code):
                            if code not in related_codes:
                                related_codes.append(code)
                        if include_siblings:
                            # Same parent = sibling
                            parent = icd10_code[:-1] if not icd10_code.endswith(".") else icd10_code[:-2]
                            if code.startswith(parent) and code not in related_codes:
                                related_codes.append(code)

            except Exception as e:
                logger.warning(f"Could not expand ICD-10 hierarchy: {e}")

        return related_codes


# Singleton instance
_indication_resolver: Optional[IndicationResolver] = None


async def get_indication_resolver(config: Optional[ResolverConfig] = None) -> IndicationResolver:
    """Get or create the indication resolver instance."""
    global _indication_resolver

    if _indication_resolver is None:
        _indication_resolver = IndicationResolver(config)
        await _indication_resolver.initialize()

    return _indication_resolver
