"""
RCSB PDB (Protein Data Bank) API Client.

Provides access to protein structure data for drug-target complexes,
antibody structures, and binding site information.

API Documentation: https://www.rcsb.org/docs/search-and-browse
Rate Limits: No explicit rate limits, but be respectful (< 5 requests/sec)
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from loguru import logger

from .base_client import APIClientConfig, BaseAPIClient
from .cache_manager import CacheManager


@dataclass
class PDBEntity:
    """An entity within a PDB structure."""
    entity_id: int
    entity_type: str  # polymer, non-polymer, water
    molecule_name: Optional[str] = None
    description: Optional[str] = None
    sequence: Optional[str] = None
    sequence_length: Optional[int] = None
    comp_id: Optional[str] = None  # For ligands
    formula: Optional[str] = None
    uniprot_ids: List[str] = field(default_factory=list)
    gene_names: List[str] = field(default_factory=list)
    is_antibody: bool = False
    antibody_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "molecule_name": self.molecule_name,
            "description": self.description,
            "sequence_length": self.sequence_length,
            "comp_id": self.comp_id,
            "formula": self.formula,
            "uniprot_ids": self.uniprot_ids,
            "gene_names": self.gene_names,
            "is_antibody": self.is_antibody,
            "antibody_type": self.antibody_type,
        }


@dataclass
class PDBStructure:
    """A protein structure from RCSB PDB."""
    pdb_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    experimental_method: Optional[str] = None
    resolution: Optional[float] = None
    deposit_date: Optional[date] = None
    release_date: Optional[date] = None
    classification: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    organism_scientific: Optional[str] = None
    organism_common: Optional[str] = None
    organism_tax_id: Optional[int] = None
    num_atoms: Optional[int] = None
    num_chains: Optional[int] = None
    molecular_weight: Optional[float] = None
    pubmed_ids: List[int] = field(default_factory=list)
    doi: Optional[str] = None
    entities: List[PDBEntity] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pdb_id": self.pdb_id,
            "title": self.title,
            "description": self.description,
            "experimental_method": self.experimental_method,
            "resolution": self.resolution,
            "deposit_date": str(self.deposit_date) if self.deposit_date else None,
            "release_date": str(self.release_date) if self.release_date else None,
            "classification": self.classification,
            "keywords": self.keywords,
            "organism_scientific": self.organism_scientific,
            "organism_tax_id": self.organism_tax_id,
            "num_chains": self.num_chains,
            "molecular_weight": self.molecular_weight,
            "pubmed_ids": self.pubmed_ids,
            "doi": self.doi,
            "entities": [e.to_dict() for e in self.entities],
        }


class RCSBPDBClient(BaseAPIClient[Dict[str, Any]]):
    """
    Client for RCSB PDB API.

    Provides access to:
    - Protein structures
    - Ligand binding sites
    - Antibody structures
    - Drug-target complexes
    """

    BASE_URL = "https://data.rcsb.org"
    SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2"

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        config = APIClientConfig(
            base_url=self.BASE_URL,
            timeout=60.0,  # PDB queries can be slow
            max_retries=3,
            requests_per_second=5.0,
            cache_ttl=604800,  # 7 days
        )
        super().__init__(config, cache_manager)

    async def health_check(self) -> bool:
        """Check if RCSB PDB API is accessible."""
        try:
            result = await self._get("/rest/v1/core/entry/6WGL")
            return "rcsb_id" in result
        except Exception as e:
            logger.error(f"RCSB PDB health check failed: {e}")
            return False

    async def get_structure(self, pdb_id: str) -> Optional[PDBStructure]:
        """
        Get detailed structure information.

        Args:
            pdb_id: PDB identifier (e.g., '6WGL')

        Returns:
            PDBStructure with detailed information
        """
        pdb_id = pdb_id.upper()
        try:
            # Get entry data
            entry = await self._get(f"/rest/v1/core/entry/{pdb_id}")

            if not entry:
                return None

            # Parse basic info
            rcsb_entry = entry.get("rcsb_entry_info", {})
            struct_info = entry.get("struct", {})
            entry.get("cell", {})
            exptl = entry.get("exptl", [{}])[0] if entry.get("exptl") else {}
            reflns = entry.get("reflns", [{}])[0] if entry.get("reflns") else {}

            # Parse dates
            deposit_date = None
            release_date = None
            if entry.get("rcsb_accession_info", {}).get("deposit_date"):
                try:
                    deposit_date = datetime.fromisoformat(
                        entry["rcsb_accession_info"]["deposit_date"].replace("Z", "+00:00")
                    ).date()
                except (ValueError, TypeError):
                    pass
            if entry.get("rcsb_accession_info", {}).get("initial_release_date"):
                try:
                    release_date = datetime.fromisoformat(
                        entry["rcsb_accession_info"]["initial_release_date"].replace("Z", "+00:00")
                    ).date()
                except (ValueError, TypeError):
                    pass

            # Get pubmed IDs
            pubmed_ids = []
            for citation in entry.get("citation", []):
                if citation.get("pdbx_database_id_PubMed"):
                    pubmed_ids.append(int(citation["pdbx_database_id_PubMed"]))

            structure = PDBStructure(
                pdb_id=pdb_id,
                title=struct_info.get("title"),
                experimental_method=exptl.get("method"),
                resolution=reflns.get("d_resolution_high"),
                deposit_date=deposit_date,
                release_date=release_date,
                classification=rcsb_entry.get("struct_keywords"),
                keywords=entry.get("struct_keywords", {}).get("pdbx_keywords", "").split(",") if entry.get("struct_keywords") else [],
                organism_scientific=entry.get("rcsb_entry_container_identifiers", {}).get("source_organism_names", [None])[0] if entry.get("rcsb_entry_container_identifiers") else None,
                num_atoms=rcsb_entry.get("deposited_atom_count"),
                num_chains=rcsb_entry.get("deposited_polymer_entity_instance_count"),
                molecular_weight=rcsb_entry.get("molecular_weight"),
                pubmed_ids=pubmed_ids,
                doi=entry.get("citation", [{}])[0].get("pdbx_database_id_DOI") if entry.get("citation") else None,
            )

            # Get entities
            structure.entities = await self._get_entities(pdb_id)

            return structure

        except Exception as e:
            logger.error(f"Error fetching PDB structure {pdb_id}: {e}")
            return None

    async def _get_entities(self, pdb_id: str) -> List[PDBEntity]:
        """Get entities for a structure."""
        entities = []
        try:
            # First get the entry to find entity IDs
            entry = await self._get(f"/rest/v1/core/entry/{pdb_id}")
            if not entry:
                return entities

            # Get polymer entity count from entry info
            rcsb_entry = entry.get("rcsb_entry_info", {})
            polymer_count = rcsb_entry.get("deposited_polymer_entity_instance_count", 0)

            # Fetch each polymer entity (entity IDs are 1-indexed)
            for entity_id in range(1, min(polymer_count + 1, 10)):  # Limit to first 10
                try:
                    entity_data = await self._get(f"/rest/v1/core/polymer_entity/{pdb_id}/{entity_id}")
                    if entity_data:
                        entities.append(self._parse_polymer_entity(entity_data))
                except Exception as e:
                    logger.debug(f"Error fetching entity {entity_id} for {pdb_id}: {e}")

        except Exception as e:
            logger.debug(f"Error fetching entities for {pdb_id}: {e}")

        return entities

    def _parse_polymer_entity(self, entity: Dict) -> PDBEntity:
        """Parse a polymer entity from API response."""
        entity_poly = entity.get("entity_poly", {})
        rcsb_entity = entity.get("rcsb_polymer_entity", {})

        # Check if it's an antibody
        is_antibody = False
        antibody_type = None
        name = rcsb_entity.get("pdbx_description", "")
        if any(term in name.lower() for term in ["antibody", "fab", "fv", "immunoglobulin", "igg"]):
            is_antibody = True
            if "fab" in name.lower():
                antibody_type = "Fab"
            elif "scfv" in name.lower():
                antibody_type = "scFv"
            elif "vhh" in name.lower() or "nanobody" in name.lower():
                antibody_type = "VHH"

        # Get UniProt IDs
        uniprot_ids = []
        for ref in entity.get("rcsb_polymer_entity_container_identifiers", {}).get("uniprot_ids", []):
            uniprot_ids.append(ref)

        return PDBEntity(
            entity_id=entity.get("rcsb_id", "").split("_")[-1] if entity.get("rcsb_id") else 0,
            entity_type="polymer",
            molecule_name=rcsb_entity.get("pdbx_description"),
            sequence=entity_poly.get("pdbx_seq_one_letter_code_can"),
            sequence_length=entity_poly.get("rcsb_sample_sequence_length"),
            uniprot_ids=uniprot_ids,
            is_antibody=is_antibody,
            antibody_type=antibody_type,
        )

    async def search_by_drug(
        self,
        drug_name: str,
        limit: int = 20,
    ) -> List[PDBStructure]:
        """
        Search for structures containing a drug as ligand.

        Args:
            drug_name: Drug name to search
            limit: Maximum results

        Returns:
            List of PDB structures
        """
        # Use full-text search which is more flexible
        query = {
            "query": {
                "type": "terminal",
                "service": "full_text",
                "parameters": {
                    "value": drug_name
                }
            },
            "return_type": "entry",
            "request_options": {
                "paginate": {
                    "start": 0,
                    "rows": limit
                },
                "sort": [{"sort_by": "score", "direction": "desc"}]
            }
        }

        try:
            # Use search API (different base URL)
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.SEARCH_URL}/query",
                    json=query,
                    headers={"Content-Type": "application/json"}
                )

                # Check if response is successful and has content
                if response.status_code == 204 or not response.content:
                    logger.debug(f"PDB search returned no results for '{drug_name}'")
                    return []

                if response.status_code != 200:
                    logger.debug(f"PDB search returned status {response.status_code}")
                    return []

                result = response.json()

            structures = []
            for hit in result.get("result_set", []):
                pdb_id = hit.get("identifier")
                if pdb_id:
                    structure = await self.get_structure(pdb_id)
                    if structure:
                        structures.append(structure)
                        if len(structures) >= limit:
                            break

            return structures

        except Exception as e:
            logger.warning(f"PDB search for '{drug_name}': {e}")
            return []

    async def search_by_uniprot(
        self,
        uniprot_id: str,
        limit: int = 50,
    ) -> List[PDBStructure]:
        """
        Search for structures containing a specific protein.

        Args:
            uniprot_id: UniProt accession (e.g., 'P05112')
            limit: Maximum results

        Returns:
            List of PDB structures containing the protein
        """
        query = {
            "query": {
                "type": "terminal",
                "service": "text",
                "parameters": {
                    "attribute": "rcsb_polymer_entity_container_identifiers.uniprot_ids",
                    "operator": "exact_match",
                    "value": uniprot_id
                }
            },
            "return_type": "entry",
            "request_options": {
                "paginate": {
                    "start": 0,
                    "rows": limit
                }
            }
        }

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.SEARCH_URL}/query",
                    json=query
                )
                response.raise_for_status()
                result = response.json()

            structures = []
            for hit in result.get("result_set", []):
                pdb_id = hit.get("identifier")
                if pdb_id:
                    structure = await self.get_structure(pdb_id)
                    if structure:
                        structures.append(structure)

            return structures

        except Exception as e:
            logger.error(f"Error searching PDB for UniProt '{uniprot_id}': {e}")
            return []

    async def search_antibody_structures(
        self,
        target_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[PDBStructure]:
        """
        Search for antibody structures, optionally filtered by target.

        Args:
            target_name: Optional target name to filter by
            limit: Maximum results

        Returns:
            List of antibody PDB structures
        """
        # Search for structures with antibody-related keywords
        query_value = "antibody immunoglobulin Fab scFv"
        if target_name:
            query_value = f"{query_value} {target_name}"

        query = {
            "query": {
                "type": "terminal",
                "service": "full_text",
                "parameters": {
                    "value": query_value
                }
            },
            "return_type": "entry",
            "request_options": {
                "paginate": {
                    "start": 0,
                    "rows": limit
                }
            }
        }

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.SEARCH_URL}/query",
                    json=query,
                    headers={"Content-Type": "application/json"}
                )

                # Check if response is successful and has content
                if response.status_code == 204 or not response.content:
                    logger.debug("PDB antibody search returned no results")
                    return []

                if response.status_code != 200:
                    logger.debug(f"PDB antibody search returned status {response.status_code}")
                    return []

                result = response.json()

            structures = []
            for hit in result.get("result_set", []):
                pdb_id = hit.get("identifier")
                if pdb_id:
                    structure = await self.get_structure(pdb_id)
                    if structure and any(e.is_antibody for e in structure.entities):
                        structures.append(structure)
                        if len(structures) >= limit:
                            break

            return structures

        except Exception as e:
            logger.error(f"Error searching PDB for antibodies: {e}")
            return []


async def get_rcsb_pdb_client(
    cache_manager: Optional[CacheManager] = None
) -> RCSBPDBClient:
    """Factory function to get RCSB PDB client instance."""
    return RCSBPDBClient(cache_manager)
