"""
RxNorm API Client.

Provides access to RxNorm for drug normalization:
- Drug name normalization
- RxCUI lookups
- Ingredient identification
- NDC to RxCUI mapping
- Drug class lookups (ATC, VA, etc.)

API Documentation: https://lhncbc.nlm.nih.gov/RxNav/APIs/
Rate Limit: No official limit, but be conservative (10 req/sec)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger

from .base_client import APIClientConfig, BaseAPIClient, APIResponse
from .cache_manager import CacheManager


@dataclass
class RxNormConcept:
    """An RxNorm concept (RxCUI)."""

    rxcui: str  # RxNorm Concept Unique Identifier
    name: str  # Normalized drug name
    tty: str  # Term type (e.g., "SCD", "SBD", "IN", "BN")
    synonym: Optional[str] = None
    suppress: Optional[str] = None

    # Expanded info
    ingredients: List[str] = field(default_factory=list)
    brand_names: List[str] = field(default_factory=list)

    def is_ingredient(self) -> bool:
        """Check if this is an ingredient concept."""
        return self.tty in ["IN", "MIN", "PIN"]

    def is_brand(self) -> bool:
        """Check if this is a brand name concept."""
        return self.tty in ["BN", "SBD", "BPCK"]

    def is_clinical_drug(self) -> bool:
        """Check if this is a clinical drug concept."""
        return self.tty in ["SCD", "SCDC", "SCDF", "SCDG"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rxcui": self.rxcui,
            "name": self.name,
            "tty": self.tty,
            "synonym": self.synonym,
            "suppress": self.suppress,
            "ingredients": self.ingredients,
            "brand_names": self.brand_names,
            "is_ingredient": self.is_ingredient(),
            "is_brand": self.is_brand(),
            "is_clinical_drug": self.is_clinical_drug(),
        }


@dataclass
class DrugClass:
    """A drug class from RxClass."""

    class_id: str
    class_name: str
    class_type: str  # "ATC", "VA", "MESH", "EPC", etc.
    rel_source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "class_id": self.class_id,
            "class_name": self.class_name,
            "class_type": self.class_type,
            "rel_source": self.rel_source,
        }


@dataclass
class DrugInteraction:
    """A drug-drug interaction."""

    drug1_rxcui: str
    drug1_name: str
    drug2_rxcui: str
    drug2_name: str
    severity: Optional[str] = None
    description: Optional[str] = None
    source: str = "DrugBank"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "drug1_rxcui": self.drug1_rxcui,
            "drug1_name": self.drug1_name,
            "drug2_rxcui": self.drug2_rxcui,
            "drug2_name": self.drug2_name,
            "severity": self.severity,
            "description": self.description,
            "source": self.source,
        }


class RxNormClient(BaseAPIClient[Dict[str, Any]]):
    """
    Client for RxNorm and RxClass REST APIs.

    No API key required - public access.

    Usage:
        client = RxNormClient()
        rxcui = await client.get_rxcui("aspirin")
        ingredients = await client.get_ingredients("857005")
    """

    # Term types
    TTY_INGREDIENT = "IN"      # Ingredient
    TTY_MIN = "MIN"            # Multiple ingredients
    TTY_PIN = "PIN"            # Precise ingredient
    TTY_BRAND = "BN"           # Brand name
    TTY_SCD = "SCD"            # Semantic clinical drug
    TTY_SBD = "SBD"            # Semantic branded drug
    TTY_SCDC = "SCDC"          # Semantic clinical drug component
    TTY_SBDC = "SBDC"          # Semantic branded drug component

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        config = APIClientConfig(
            base_url="https://rxnav.nlm.nih.gov/REST",
            timeout=30.0,
            max_retries=3,
            requests_per_second=10.0,
            cache_ttl=604800,  # 7 days (RxNorm updates weekly)
        )
        super().__init__(config, cache_manager)

    async def health_check(self) -> bool:
        """Check if RxNorm API is accessible."""
        try:
            result = await self._get("/rxcui.json", params={"name": "aspirin"}, use_cache=False)
            return "idGroup" in result
        except Exception as e:
            logger.error(f"RxNorm health check failed: {e}")
            return False

    async def get_rxcui(self, name: str, search_type: int = 0) -> Optional[str]:
        """
        Get RxCUI for a drug name.

        Args:
            name: Drug name to search
            search_type: 0=exact, 1=normalized, 2=approximate

        Returns:
            RxCUI string or None if not found
        """
        try:
            # Use .json extension to get JSON response (default is XML)
            result = await self._get(
                "/rxcui.json",
                params={"name": name, "search": search_type}
            )

            id_group = result.get("idGroup", {})
            rxn_ids = id_group.get("rxnormId", [])

            if rxn_ids:
                return rxn_ids[0]  # Return first match
            return None
        except Exception as e:
            logger.error(f"Error getting RxCUI for '{name}': {e}")
            return None

    async def approximate_match(
        self,
        name: str,
        max_entries: int = 10
    ) -> List[RxNormConcept]:
        """
        Find approximate matches for a drug name.

        Args:
            name: Drug name to search
            max_entries: Maximum results to return

        Returns:
            List of matching concepts
        """
        try:
            result = await self._get(
                "/approximateTerm",
                params={"term": name, "maxEntries": max_entries}
            )

            concepts = []
            candidates = result.get("approximateGroup", {}).get("candidate", [])

            for item in candidates:
                concepts.append(RxNormConcept(
                    rxcui=item.get("rxcui", ""),
                    name=item.get("name", ""),
                    tty=item.get("tty", ""),
                ))

            return concepts
        except Exception as e:
            logger.error(f"Error in approximate match for '{name}': {e}")
            return []

    async def get_concept(self, rxcui: str) -> Optional[RxNormConcept]:
        """
        Get concept details by RxCUI.

        Args:
            rxcui: RxNorm Concept Unique Identifier

        Returns:
            RxNormConcept or None
        """
        try:
            result = await self._get(f"/rxcui/{rxcui}/properties")

            props = result.get("properties", {})
            if not props:
                return None

            return RxNormConcept(
                rxcui=props.get("rxcui", rxcui),
                name=props.get("name", ""),
                tty=props.get("tty", ""),
                synonym=props.get("synonym"),
                suppress=props.get("suppress"),
            )
        except Exception as e:
            logger.error(f"Error getting concept for RxCUI {rxcui}: {e}")
            return None

    async def get_all_properties(self, rxcui: str) -> Dict[str, Any]:
        """
        Get all properties for an RxCUI.

        Args:
            rxcui: RxNorm Concept Unique Identifier

        Returns:
            Dictionary of all properties
        """
        try:
            result = await self._get(f"/rxcui/{rxcui}/allProperties", params={"prop": "all"})
            return result.get("propConceptGroup", {}).get("propConcept", [])
        except Exception as e:
            logger.error(f"Error getting all properties for {rxcui}: {e}")
            return {}

    async def get_ingredients(self, rxcui: str) -> List[RxNormConcept]:
        """
        Get ingredients for a drug.

        Args:
            rxcui: RxCUI of drug product

        Returns:
            List of ingredient concepts
        """
        try:
            result = await self._get(
                f"/rxcui/{rxcui}/related",
                params={"tty": "IN+MIN+PIN"}
            )

            ingredients = []
            for group in result.get("relatedGroup", {}).get("conceptGroup", []):
                for prop in group.get("conceptProperties", []):
                    ingredients.append(RxNormConcept(
                        rxcui=prop.get("rxcui", ""),
                        name=prop.get("name", ""),
                        tty=prop.get("tty", ""),
                    ))

            return ingredients
        except Exception as e:
            logger.error(f"Error getting ingredients for {rxcui}: {e}")
            return []

    async def get_brands(self, rxcui: str) -> List[RxNormConcept]:
        """
        Get brand name products for an ingredient.

        Args:
            rxcui: RxCUI of ingredient

        Returns:
            List of brand name concepts
        """
        try:
            # Use separate TTY values - the + syntax doesn't work well with URL encoding
            result = await self._get(
                f"/rxcui/{rxcui}/related.json",
                params={"tty": "BN SBD BPCK"}
            )

            brands = []
            for group in result.get("relatedGroup", {}).get("conceptGroup", []):
                for prop in group.get("conceptProperties", []):
                    brands.append(RxNormConcept(
                        rxcui=prop.get("rxcui", ""),
                        name=prop.get("name", ""),
                        tty=prop.get("tty", ""),
                    ))

            return brands
        except Exception as e:
            logger.debug(f"RxNorm brands for {rxcui}: {e}")
            return []

    async def get_ndc_codes(self, rxcui: str) -> List[str]:
        """
        Get NDC codes for an RxCUI.

        Args:
            rxcui: RxNorm Concept Unique Identifier

        Returns:
            List of NDC codes
        """
        try:
            result = await self._get(f"/rxcui/{rxcui}/ndcs.json")
            return result.get("ndcGroup", {}).get("ndcList", {}).get("ndc", [])
        except Exception as e:
            logger.error(f"Error getting NDCs for {rxcui}: {e}")
            return []

    async def ndc_to_rxcui(self, ndc: str) -> Optional[str]:
        """
        Map NDC to RxCUI.

        Args:
            ndc: National Drug Code

        Returns:
            RxCUI or None
        """
        try:
            result = await self._get("/ndcstatus", params={"ndc": ndc})

            status = result.get("ndcStatus", {})
            return status.get("rxcui")
        except Exception as e:
            logger.error(f"Error mapping NDC {ndc}: {e}")
            return None

    async def get_drug_classes(
        self,
        rxcui: str,
        class_types: Optional[List[str]] = None
    ) -> List[DrugClass]:
        """
        Get drug classes for an RxCUI from RxClass.

        Args:
            rxcui: RxNorm Concept Unique Identifier
            class_types: Filter by class types (ATC, VA, MESH, EPC, etc.)

        Returns:
            List of drug classes
        """
        params = {"rxcui": rxcui}
        if class_types:
            params["classTypes"] = "+".join(class_types)

        try:
            result = await self._get(
                "/rxclass/class/byRxcui.json",
                params=params
            )

            classes = []
            for group in result.get("rxclassDrugInfoList", {}).get("rxclassDrugInfo", []):
                class_info = group.get("rxclassMinConceptItem", {})
                classes.append(DrugClass(
                    class_id=class_info.get("classId", ""),
                    class_name=class_info.get("className", ""),
                    class_type=class_info.get("classType", ""),
                    rel_source=group.get("rela"),
                ))

            return classes
        except Exception as e:
            logger.error(f"Error getting drug classes for {rxcui}: {e}")
            return []

    async def get_atc_codes(self, rxcui: str) -> List[str]:
        """
        Get ATC codes for an RxCUI.

        Args:
            rxcui: RxNorm Concept Unique Identifier

        Returns:
            List of ATC codes
        """
        classes = await self.get_drug_classes(rxcui, class_types=["ATC"])
        return [c.class_id for c in classes]

    async def get_interactions(
        self,
        rxcui: str,
        sources: Optional[List[str]] = None
    ) -> List[DrugInteraction]:
        """
        Get drug interactions for an RxCUI.

        Args:
            rxcui: RxNorm Concept Unique Identifier
            sources: Interaction sources (e.g., "DrugBank", "ONCHigh")

        Returns:
            List of drug interactions
        """
        params = {"rxcui": rxcui}
        if sources:
            params["sources"] = "+".join(sources)

        try:
            result = await self._get("/interaction/interaction.json", params=params)

            interactions = []
            for group in result.get("interactionTypeGroup", []):
                source = group.get("sourceName", "")

                for type_info in group.get("interactionType", []):
                    for pair in type_info.get("interactionPair", []):
                        concepts = pair.get("interactionConcept", [])
                        if len(concepts) >= 2:
                            interactions.append(DrugInteraction(
                                drug1_rxcui=concepts[0].get("minConceptItem", {}).get("rxcui", ""),
                                drug1_name=concepts[0].get("minConceptItem", {}).get("name", ""),
                                drug2_rxcui=concepts[1].get("minConceptItem", {}).get("rxcui", ""),
                                drug2_name=concepts[1].get("minConceptItem", {}).get("name", ""),
                                severity=pair.get("severity"),
                                description=pair.get("description"),
                                source=source,
                            ))

            return interactions
        except Exception as e:
            logger.debug(f"RxNorm interactions for {rxcui}: {e}")
            return []

    async def get_drugs_by_class(
        self,
        class_id: str,
        class_type: str = "ATC"
    ) -> List[RxNormConcept]:
        """
        Get drugs belonging to a class.

        Args:
            class_id: Class identifier (e.g., ATC code)
            class_type: Type of class (ATC, VA, MESH, etc.)

        Returns:
            List of drug concepts
        """
        try:
            result = await self._get(
                "/rxclass/classMembers",
                params={
                    "classId": class_id,
                    "relaSource": class_type,
                }
            )

            drugs = []
            for member in result.get("drugMemberGroup", {}).get("drugMember", []):
                concept = member.get("minConcept", {})
                drugs.append(RxNormConcept(
                    rxcui=concept.get("rxcui", ""),
                    name=concept.get("name", ""),
                    tty=concept.get("tty", ""),
                ))

            return drugs
        except Exception as e:
            logger.error(f"Error getting drugs for class {class_id}: {e}")
            return []

    async def search_by_ingredient_class(
        self,
        ingredient: str,
        limit: int = 20,
    ) -> "APIResponse":
        """
        Search for drugs by ingredient class (target-related search).

        Args:
            ingredient: Ingredient or target name to search
            limit: Maximum results

        Returns:
            APIResponse with drugs related to the ingredient
        """
        from .base_client import APIResponse

        try:
            # First find the ingredient's RxCUI
            rxcui = await self.get_rxcui(ingredient)
            if not rxcui:
                return APIResponse(success=False, error=f"No RxCUI found for {ingredient}")

            # Get related drugs (same ingredient base)
            related = await self.get_ingredients(rxcui)

            drugs = []
            for concept in related[:limit]:
                drugs.append({
                    "name": concept.name,
                    "rxcui": concept.rxcui,
                    "tty": concept.tty,
                })

            return APIResponse(
                success=True,
                data={"drugs": drugs, "total": len(drugs)},
            )

        except Exception as e:
            logger.error(f"Error searching by ingredient class: {e}")
            return APIResponse(success=False, error=str(e))

    async def normalize_drug_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Normalize a drug name using RxNorm.

        Returns the most specific concept (ingredient, clinical drug, or brand)
        along with standardized name and identifiers.

        Args:
            name: Drug name to normalize

        Returns:
            Normalized drug info or None
        """
        # Try exact match first
        rxcui = await self.get_rxcui(name, search_type=0)

        # Fall back to normalized match
        if not rxcui:
            rxcui = await self.get_rxcui(name, search_type=1)

        # Fall back to approximate match
        if not rxcui:
            matches = await self.approximate_match(name, max_entries=1)
            if matches:
                rxcui = matches[0].rxcui

        if not rxcui:
            return None

        concept = await self.get_concept(rxcui)
        if not concept:
            return None

        # Get ingredients
        ingredients = await self.get_ingredients(rxcui)

        # Get ATC codes
        atc_codes = await self.get_atc_codes(rxcui)

        return {
            "original_name": name,
            "normalized_name": concept.name,
            "rxcui": concept.rxcui,
            "term_type": concept.tty,
            "is_ingredient": concept.is_ingredient(),
            "is_brand": concept.is_brand(),
            "ingredients": [{"rxcui": i.rxcui, "name": i.name} for i in ingredients],
            "atc_codes": atc_codes,
        }


# Singleton instance
_rxnorm_client: Optional[RxNormClient] = None


async def get_rxnorm_client(cache_manager: Optional[CacheManager] = None) -> RxNormClient:
    """Get or create the RxNorm client instance."""
    global _rxnorm_client

    if _rxnorm_client is None:
        _rxnorm_client = RxNormClient(cache_manager)

    return _rxnorm_client
