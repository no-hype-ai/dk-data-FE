"""
UniProt API Client.

Provides access to protein data from UniProt:
- Protein sequence and structure information
- Functional annotations
- Drug-target relationships
- Cross-references to PDB, ChEMBL, DrugBank

API Documentation: https://www.uniprot.org/help/programmatic_access
Rate Limits: No explicit limits, but use reasonable request rates
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from loguru import logger

from .base_client import APIClientConfig, BaseAPIClient
from .cache_manager import CacheManager


@dataclass
class UniProtFeature:
    """A feature/annotation on a protein sequence."""
    feature_type: str  # Domain, Binding site, Active site, etc.
    description: Optional[str] = None
    start_position: Optional[int] = None
    end_position: Optional[int] = None
    evidence: Optional[str] = None
    feature_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_type": self.feature_type,
            "description": self.description,
            "start_position": self.start_position,
            "end_position": self.end_position,
            "evidence": self.evidence,
            "feature_id": self.feature_id,
        }


@dataclass
class UniProtCrossReference:
    """A cross-reference to another database."""
    database: str
    identifier: str
    properties: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "database": self.database,
            "identifier": self.identifier,
            "properties": self.properties,
        }


@dataclass
class UniProtProtein:
    """A protein entry from UniProt."""
    accession: str  # Primary accession (e.g., P05112)
    entry_name: Optional[str] = None  # e.g., IL4_HUMAN
    protein_name: Optional[str] = None
    gene_names: List[str] = field(default_factory=list)
    organism: Optional[str] = None
    organism_id: Optional[int] = None
    sequence: Optional[str] = None
    sequence_length: Optional[int] = None
    mass: Optional[int] = None  # Molecular mass in Da

    # Functional annotation
    function_description: Optional[str] = None
    catalytic_activity: List[str] = field(default_factory=list)
    pathway: List[str] = field(default_factory=list)
    subcellular_location: List[str] = field(default_factory=list)
    disease_involvement: List[str] = field(default_factory=list)

    # Classification
    protein_families: List[str] = field(default_factory=list)
    go_terms: List[Dict[str, str]] = field(default_factory=list)
    ec_numbers: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)

    # Cross-references
    pdb_ids: List[str] = field(default_factory=list)
    chembl_id: Optional[str] = None
    drugbank_ids: List[str] = field(default_factory=list)

    # Features
    features: List[UniProtFeature] = field(default_factory=list)
    cross_references: List[UniProtCrossReference] = field(default_factory=list)

    # Status
    reviewed: bool = False  # Swiss-Prot (reviewed) vs TrEMBL (unreviewed)
    annotation_score: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accession": self.accession,
            "entry_name": self.entry_name,
            "protein_name": self.protein_name,
            "gene_names": self.gene_names,
            "organism": self.organism,
            "organism_id": self.organism_id,
            "sequence_length": self.sequence_length,
            "mass": self.mass,
            "function_description": self.function_description,
            "pathway": self.pathway,
            "subcellular_location": self.subcellular_location,
            "disease_involvement": self.disease_involvement,
            "protein_families": self.protein_families,
            "go_terms": self.go_terms,
            "ec_numbers": self.ec_numbers,
            "keywords": self.keywords,
            "pdb_ids": self.pdb_ids,
            "chembl_id": self.chembl_id,
            "drugbank_ids": self.drugbank_ids,
            "reviewed": self.reviewed,
            "annotation_score": self.annotation_score,
            "features": [f.to_dict() for f in self.features],
        }


class UniProtClient(BaseAPIClient[Dict[str, Any]]):
    """
    Client for UniProt REST API.

    Provides access to:
    - Protein entries and sequences
    - Functional annotations
    - Cross-references to drug databases
    - Protein features (domains, binding sites)
    """

    BASE_URL = "https://rest.uniprot.org"

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        config = APIClientConfig(
            base_url=self.BASE_URL,
            timeout=60.0,  # UniProt queries can be slow
            max_retries=3,
            requests_per_second=5.0,
            cache_ttl=604800,  # 7 days
        )
        super().__init__(config, cache_manager)

    async def health_check(self) -> bool:
        """Check if UniProt API is accessible."""
        try:
            result = await self._get("/uniprotkb/P05112.json")
            return "primaryAccession" in result
        except Exception as e:
            logger.error(f"UniProt health check failed: {e}")
            return False

    async def get_protein(self, accession: str) -> Optional[UniProtProtein]:
        """
        Get protein entry by UniProt accession.

        Args:
            accession: UniProt accession (e.g., 'P05112')

        Returns:
            UniProtProtein with detailed information
        """
        try:
            data = await self._get(f"/uniprotkb/{accession}.json")

            if not data:
                return None

            return self._parse_protein(data)

        except Exception as e:
            logger.error(f"Error fetching UniProt entry {accession}: {e}")
            return None

    def _parse_protein(self, data: Dict) -> UniProtProtein:
        """Parse UniProt JSON response into UniProtProtein."""
        # Basic info
        accession = data.get("primaryAccession", "")
        entry_name = data.get("uniProtkbId", "")

        # Protein name
        protein_name = None
        protein_desc = data.get("proteinDescription", {})
        if protein_desc.get("recommendedName"):
            protein_name = protein_desc["recommendedName"].get("fullName", {}).get("value")
        elif protein_desc.get("submissionNames"):
            protein_name = protein_desc["submissionNames"][0].get("fullName", {}).get("value")

        # Gene names
        gene_names = []
        for gene in data.get("genes", []):
            if gene.get("geneName"):
                gene_names.append(gene["geneName"].get("value", ""))
            for syn in gene.get("synonyms", []):
                gene_names.append(syn.get("value", ""))

        # Organism
        organism = data.get("organism", {}).get("scientificName")
        organism_id = data.get("organism", {}).get("taxonId")

        # Sequence
        sequence = data.get("sequence", {}).get("value")
        sequence_length = data.get("sequence", {}).get("length")
        mass = data.get("sequence", {}).get("molWeight")

        # Function description
        function_description = None
        for comment in data.get("comments", []):
            if comment.get("commentType") == "FUNCTION":
                texts = comment.get("texts", [])
                if texts:
                    function_description = texts[0].get("value")
                break

        # Subcellular location
        subcellular_location = []
        for comment in data.get("comments", []):
            if comment.get("commentType") == "SUBCELLULAR LOCATION":
                for loc in comment.get("subcellularLocations", []):
                    if loc.get("location"):
                        subcellular_location.append(loc["location"].get("value", ""))

        # Disease involvement
        disease_involvement = []
        for comment in data.get("comments", []):
            if comment.get("commentType") == "DISEASE":
                disease = comment.get("disease", {})
                if disease.get("diseaseId"):
                    disease_involvement.append(disease.get("diseaseId"))

        # Pathway
        pathway = []
        for comment in data.get("comments", []):
            if comment.get("commentType") == "PATHWAY":
                texts = comment.get("texts", [])
                for text in texts:
                    pathway.append(text.get("value", ""))

        # Keywords
        keywords = [kw.get("name", "") for kw in data.get("keywords", [])]

        # GO terms
        go_terms = []
        for ref in data.get("uniProtKBCrossReferences", []):
            if ref.get("database") == "GO":
                go_term = {
                    "id": ref.get("id", ""),
                    "term": None,
                    "aspect": None,
                }
                for prop in ref.get("properties", []):
                    if prop.get("key") == "GoTerm":
                        parts = prop.get("value", "").split(":")
                        if len(parts) >= 2:
                            go_term["aspect"] = parts[0]
                            go_term["term"] = ":".join(parts[1:])
                go_terms.append(go_term)

        # Cross-references
        pdb_ids = []
        chembl_id = None
        drugbank_ids = []

        for ref in data.get("uniProtKBCrossReferences", []):
            db = ref.get("database", "")
            ref_id = ref.get("id", "")

            if db == "PDB":
                pdb_ids.append(ref_id)
            elif db == "ChEMBL":
                chembl_id = ref_id
            elif db == "DrugBank":
                drugbank_ids.append(ref_id)

        # Features
        features = []
        for feat in data.get("features", []):
            feature = UniProtFeature(
                feature_type=feat.get("type", ""),
                description=feat.get("description"),
                start_position=feat.get("location", {}).get("start", {}).get("value"),
                end_position=feat.get("location", {}).get("end", {}).get("value"),
                feature_id=feat.get("featureId"),
            )
            features.append(feature)

        # Status
        reviewed = data.get("entryType") == "UniProtKB reviewed (Swiss-Prot)"
        annotation_score = data.get("annotationScore")

        return UniProtProtein(
            accession=accession,
            entry_name=entry_name,
            protein_name=protein_name,
            gene_names=gene_names,
            organism=organism,
            organism_id=organism_id,
            sequence=sequence,
            sequence_length=sequence_length,
            mass=mass,
            function_description=function_description,
            subcellular_location=subcellular_location,
            disease_involvement=disease_involvement,
            pathway=pathway,
            keywords=keywords,
            go_terms=go_terms,
            pdb_ids=pdb_ids,
            chembl_id=chembl_id,
            drugbank_ids=drugbank_ids,
            features=features,
            reviewed=reviewed,
            annotation_score=annotation_score,
        )

    async def search_proteins(
        self,
        query: str,
        organism: Optional[str] = None,
        reviewed_only: bool = True,
        limit: int = 25,
    ) -> List[UniProtProtein]:
        """
        Search for proteins.

        Args:
            query: Search query (protein name, gene name, etc.)
            organism: Filter by organism (e.g., 'human', '9606')
            reviewed_only: Only return Swiss-Prot (reviewed) entries
            limit: Maximum results

        Returns:
            List of matching proteins
        """
        # Build query string
        query_parts = [query]

        if organism:
            if organism.isdigit():
                query_parts.append(f"organism_id:{organism}")
            else:
                query_parts.append(f"organism_name:{organism}")

        if reviewed_only:
            query_parts.append("reviewed:true")

        full_query = " AND ".join(query_parts)

        try:
            result = await self._get(
                "/uniprotkb/search",
                params={
                    "query": full_query,
                    "format": "json",
                    "size": limit,
                }
            )

            proteins = []
            for entry in result.get("results", []):
                proteins.append(self._parse_protein(entry))

            return proteins

        except Exception as e:
            logger.error(f"Error searching UniProt for '{query}': {e}")
            return []

    async def search_by_gene(
        self,
        gene_name: str,
        organism: str = "human",
        limit: int = 10,
    ) -> List[UniProtProtein]:
        """
        Search for proteins by gene name.

        Args:
            gene_name: Gene symbol (e.g., 'IL4', 'EGFR')
            organism: Organism filter
            limit: Maximum results

        Returns:
            List of matching proteins
        """
        query = f"gene:{gene_name}"
        return await self.search_proteins(query, organism=organism, limit=limit)

    async def get_drug_targets(
        self,
        drug_name: str,
        limit: int = 50,
    ) -> List[UniProtProtein]:
        """
        Search for proteins that are drug targets.

        Args:
            drug_name: Drug name to search
            limit: Maximum results

        Returns:
            List of target proteins
        """
        # Use simple full-text search for the drug name
        # The cc_drug and annotation queries require specific syntax
        query = f'"{drug_name}"'

        try:
            return await self.search_proteins(query, organism="human", limit=limit)
        except Exception as e:
            logger.warning(f"UniProt drug target search for '{drug_name}': {e}")
            return []

    async def get_proteins_for_disease(
        self,
        disease: str,
        organism: str = "human",
        limit: int = 50,
    ) -> List[UniProtProtein]:
        """
        Get proteins associated with a disease.

        Args:
            disease: Disease name
            organism: Organism filter
            limit: Maximum results

        Returns:
            List of associated proteins
        """
        query = f'cc_disease:"{disease}"'
        return await self.search_proteins(query, organism=organism, limit=limit)

    async def get_proteins_by_pdb(
        self,
        pdb_id: str,
    ) -> List[UniProtProtein]:
        """
        Get proteins associated with a PDB structure.

        Args:
            pdb_id: PDB identifier

        Returns:
            List of proteins in the structure
        """
        query = f"xref:pdb-{pdb_id.upper()}"
        return await self.search_proteins(query, reviewed_only=False, limit=50)

    async def get_binding_sites(
        self,
        accession: str,
    ) -> List[UniProtFeature]:
        """
        Get binding site features for a protein.

        Args:
            accession: UniProt accession

        Returns:
            List of binding site features
        """
        protein = await self.get_protein(accession)
        if not protein:
            return []

        binding_features = [
            f for f in protein.features
            if f.feature_type.lower() in ['binding site', 'active site', 'metal binding']
        ]

        return binding_features

    async def get_domains(
        self,
        accession: str,
    ) -> List[UniProtFeature]:
        """
        Get domain features for a protein.

        Args:
            accession: UniProt accession

        Returns:
            List of domain features
        """
        protein = await self.get_protein(accession)
        if not protein:
            return []

        domain_features = [
            f for f in protein.features
            if f.feature_type.lower() in ['domain', 'region']
        ]

        return domain_features


async def get_uniprot_client(
    cache_manager: Optional[CacheManager] = None
) -> UniProtClient:
    """Factory function to get UniProt client instance."""
    return UniProtClient(cache_manager)
