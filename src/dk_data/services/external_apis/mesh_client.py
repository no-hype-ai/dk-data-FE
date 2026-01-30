"""
MeSH (Medical Subject Headings) API Client.

Implements T025: MeSHClient for medical terminology
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import aiohttp
from loguru import logger

from .base_client import BaseAPIClient, APIResponse, APIClientConfig


@dataclass
class MeSHTerm:
    """MeSH term data structure."""
    descriptor_ui: str  # Unique identifier (e.g., D000001)
    name: str
    tree_numbers: List[str] = field(default_factory=list)
    scope_note: Optional[str] = None
    synonyms: List[str] = field(default_factory=list)
    parent_terms: List[str] = field(default_factory=list)
    child_terms: List[str] = field(default_factory=list)
    pharmacological_actions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "descriptor_ui": self.descriptor_ui,
            "name": self.name,
            "tree_numbers": self.tree_numbers,
            "scope_note": self.scope_note,
            "synonyms": self.synonyms,
            "parent_terms": self.parent_terms,
            "child_terms": self.child_terms,
            "pharmacological_actions": self.pharmacological_actions,
        }


@dataclass
class TherapeuticClass:
    """Therapeutic classification from MeSH."""
    class_id: str
    name: str
    description: Optional[str] = None
    parent_class: Optional[str] = None
    child_classes: List[str] = field(default_factory=list)
    drugs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "class_id": self.class_id,
            "name": self.name,
            "description": self.description,
            "parent_class": self.parent_class,
            "child_classes": self.child_classes,
            "drugs": self.drugs,
        }


class MeSHClient(BaseAPIClient):
    """
    Client for NLM MeSH API.

    Free API for medical terminology lookups.
    Rate limit: 3 requests/second
    """

    BASE_URL = "https://id.nlm.nih.gov/mesh"
    SPARQL_URL = "https://id.nlm.nih.gov/mesh/sparql"

    def __init__(self, cache_ttl: int = 86400):  # 24 hour cache
        config = APIClientConfig(
            base_url=self.BASE_URL,
            requests_per_second=3.0,  # ~3 req/sec
            cache_ttl=cache_ttl,
        )
        super().__init__(config)

    async def health_check(self) -> bool:
        """
        Check if the MeSH API is healthy and accessible.

        Returns:
            True if API is healthy, False otherwise
        """
        try:
            result = await self.lookup_term("aspirin")
            return result.success
        except Exception as e:
            logger.warning(f"MeSH API health check failed: {e}")
            return False

    async def lookup_term(self, term: str) -> APIResponse:
        """
        Look up a MeSH term by name.

        Args:
            term: Term name to look up

        Returns:
            APIResponse with MeSH term details
        """
        # Use the lookup endpoint
        url = f"{self.BASE_URL}/lookup/descriptor"
        params = {
            "label": term,
            "match": "contains",
            "limit": 10,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        terms = self._parse_lookup_results(data)
                        return APIResponse(
                            success=True,
                            data={
                                "terms": [t.to_dict() for t in terms],
                                "count": len(terms),
                            },
                            source="mesh",
                        )
                    else:
                        return APIResponse(
                            success=False,
                            error=f"Lookup failed: {response.status}",
                            source="mesh",
                        )
        except Exception as e:
            logger.error(f"MeSH lookup failed: {e}")
            return APIResponse(success=False, error=str(e), source="mesh")

    async def get_descriptor(self, descriptor_ui: str) -> APIResponse:
        """
        Get detailed information for a MeSH descriptor.

        Args:
            descriptor_ui: MeSH descriptor UI (e.g., D000001)

        Returns:
            APIResponse with descriptor details
        """
        url = f"{self.BASE_URL}/{descriptor_ui}.json"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        term = self._parse_descriptor(data, descriptor_ui)
                        if term:
                            return APIResponse(
                                success=True,
                                data=term.to_dict(),
                                source="mesh",
                            )
                        return APIResponse(
                            success=False,
                            error="Failed to parse descriptor",
                            source="mesh",
                        )
                    elif response.status == 404:
                        return APIResponse(
                            success=False,
                            error="Descriptor not found",
                            source="mesh",
                        )
                    else:
                        return APIResponse(
                            success=False,
                            error=f"API error: {response.status}",
                            source="mesh",
                        )
        except Exception as e:
            logger.error(f"MeSH descriptor fetch failed: {e}")
            return APIResponse(success=False, error=str(e), source="mesh")

    async def get_pharmacological_class(self, drug_term: str) -> APIResponse:
        """
        Get pharmacological classification for a drug.

        Args:
            drug_term: Drug name or MeSH term

        Returns:
            APIResponse with therapeutic classes
        """
        # First lookup the term
        lookup_result = await self.lookup_term(drug_term)
        if not lookup_result.success or not lookup_result.data.get("terms"):
            return APIResponse(
                success=False,
                error="Drug term not found in MeSH",
                source="mesh",
            )

        # Get the first matching descriptor
        first_term = lookup_result.data["terms"][0]
        descriptor_ui = first_term.get("descriptor_ui")

        if not descriptor_ui:
            return APIResponse(
                success=False,
                error="No descriptor UI found",
                source="mesh",
            )

        # Get full descriptor with pharmacological actions
        descriptor_result = await self.get_descriptor(descriptor_ui)
        if not descriptor_result.success:
            return descriptor_result

        pharm_actions = descriptor_result.data.get("pharmacological_actions", [])

        # Build therapeutic class hierarchy
        classes = []
        for action in pharm_actions:
            tc = TherapeuticClass(
                class_id=action,
                name=action,
                drugs=[drug_term],
            )
            classes.append(tc)

        return APIResponse(
            success=True,
            data={
                "drug": drug_term,
                "descriptor_ui": descriptor_ui,
                "therapeutic_classes": [c.to_dict() for c in classes],
            },
            source="mesh",
        )

    async def get_tree_hierarchy(self, tree_number: str) -> APIResponse:
        """
        Get the hierarchy for a MeSH tree number.

        Args:
            tree_number: MeSH tree number (e.g., D03.383.129)

        Returns:
            APIResponse with hierarchy
        """
        # SPARQL query to get hierarchy
        query = f"""
        PREFIX mesh: <http://id.nlm.nih.gov/mesh/>
        PREFIX meshv: <http://id.nlm.nih.gov/mesh/vocab#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

        SELECT ?descriptor ?label ?treeNum
        WHERE {{
            ?descriptor meshv:treeNumber ?treeNum .
            ?descriptor rdfs:label ?label .
            FILTER(STRSTARTS(STR(?treeNum), "{tree_number}"))
        }}
        ORDER BY ?treeNum
        LIMIT 100
        """

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.SPARQL_URL,
                    params={"query": query, "format": "json"},
                    headers={"Accept": "application/sparql-results+json"},
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        hierarchy = self._parse_sparql_results(data)
                        return APIResponse(
                            success=True,
                            data={
                                "tree_number": tree_number,
                                "hierarchy": hierarchy,
                            },
                            source="mesh",
                        )
                    else:
                        return APIResponse(
                            success=False,
                            error=f"SPARQL query failed: {response.status}",
                            source="mesh",
                        )
        except Exception as e:
            logger.error(f"MeSH hierarchy query failed: {e}")
            return APIResponse(success=False, error=str(e), source="mesh")

    async def search_by_therapeutic_area(
        self,
        therapeutic_area: str,
        limit: int = 50,
    ) -> APIResponse:
        """
        Search for drugs in a therapeutic area.

        Args:
            therapeutic_area: Therapeutic area name
            limit: Maximum results

        Returns:
            APIResponse with drugs in the therapeutic area
        """
        # SPARQL query for drugs in therapeutic area
        query = f"""
        PREFIX mesh: <http://id.nlm.nih.gov/mesh/>
        PREFIX meshv: <http://id.nlm.nih.gov/mesh/vocab#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

        SELECT DISTINCT ?drug ?drugLabel ?pharmAction
        WHERE {{
            ?drug meshv:pharmacologicalAction ?action .
            ?action rdfs:label ?pharmAction .
            ?drug rdfs:label ?drugLabel .
            FILTER(CONTAINS(LCASE(?pharmAction), LCASE("{therapeutic_area}")))
        }}
        LIMIT {limit}
        """

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.SPARQL_URL,
                    params={"query": query, "format": "json"},
                    headers={"Accept": "application/sparql-results+json"},
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        drugs = self._parse_drug_results(data)
                        return APIResponse(
                            success=True,
                            data={
                                "therapeutic_area": therapeutic_area,
                                "drugs": drugs,
                                "count": len(drugs),
                            },
                            source="mesh",
                        )
                    else:
                        return APIResponse(
                            success=False,
                            error=f"SPARQL query failed: {response.status}",
                            source="mesh",
                        )
        except Exception as e:
            logger.error(f"MeSH therapeutic search failed: {e}")
            return APIResponse(success=False, error=str(e), source="mesh")

    def _parse_lookup_results(self, data: List[Dict]) -> List[MeSHTerm]:
        """Parse lookup API results."""
        terms = []
        for item in data:
            try:
                # Extract UI from resource URI
                resource = item.get("resource", "")
                ui = resource.split("/")[-1] if resource else ""

                term = MeSHTerm(
                    descriptor_ui=ui,
                    name=item.get("label", ""),
                )
                terms.append(term)
            except Exception as e:
                logger.warning(f"Failed to parse lookup result: {e}")
                continue
        return terms

    def _parse_descriptor(self, data: Dict, descriptor_ui: str) -> Optional[MeSHTerm]:
        """Parse descriptor JSON-LD response."""
        try:
            # JSON-LD format
            graph = data.get("@graph", [data])

            name = ""
            scope_note = None
            tree_numbers = []
            synonyms = []
            pharm_actions = []

            for item in graph:
                item_id = item.get("@id", "")
                if descriptor_ui in item_id:
                    name = item.get("label", {})
                    if isinstance(name, dict):
                        name = name.get("@value", "")
                    elif isinstance(name, list):
                        name = name[0].get("@value", "") if name else ""

                    scope_note = item.get("scopeNote", {})
                    if isinstance(scope_note, dict):
                        scope_note = scope_note.get("@value")
                    elif isinstance(scope_note, list):
                        scope_note = scope_note[0].get("@value", "") if scope_note else None

                    # Tree numbers
                    tree_nums = item.get("treeNumber", [])
                    if isinstance(tree_nums, str):
                        tree_numbers = [tree_nums]
                    elif isinstance(tree_nums, list):
                        tree_numbers = [t.get("@id", t) if isinstance(t, dict) else t for t in tree_nums]

                    # Pharmacological actions
                    actions = item.get("pharmacologicalAction", [])
                    if isinstance(actions, str):
                        pharm_actions = [actions]
                    elif isinstance(actions, list):
                        for a in actions:
                            if isinstance(a, dict):
                                pharm_actions.append(a.get("@id", "").split("/")[-1])
                            else:
                                pharm_actions.append(str(a))

            return MeSHTerm(
                descriptor_ui=descriptor_ui,
                name=name,
                tree_numbers=tree_numbers,
                scope_note=scope_note,
                synonyms=synonyms,
                pharmacological_actions=pharm_actions,
            )
        except Exception as e:
            logger.error(f"Failed to parse descriptor: {e}")
            return None

    def _parse_sparql_results(self, data: Dict) -> List[Dict]:
        """Parse SPARQL query results."""
        results = []
        bindings = data.get("results", {}).get("bindings", [])

        for binding in bindings:
            result = {}
            for key, value in binding.items():
                result[key] = value.get("value", "")
            results.append(result)

        return results

    def _parse_drug_results(self, data: Dict) -> List[Dict]:
        """Parse drug search results from SPARQL."""
        drugs = []
        bindings = data.get("results", {}).get("bindings", [])

        for binding in bindings:
            drug = {
                "uri": binding.get("drug", {}).get("value", ""),
                "name": binding.get("drugLabel", {}).get("value", ""),
                "pharmacological_action": binding.get("pharmAction", {}).get("value", ""),
            }
            # Extract descriptor UI from URI
            if drug["uri"]:
                drug["descriptor_ui"] = drug["uri"].split("/")[-1]
            drugs.append(drug)

        return drugs
