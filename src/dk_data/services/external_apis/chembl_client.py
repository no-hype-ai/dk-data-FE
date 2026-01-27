"""
ChEMBL API Client.

Provides access to ChEMBL database via their REST API:
- Molecule/compound data
- Target binding data
- Drug mechanism of action
- Assay results

API Documentation: https://www.ebi.ac.uk/chembl/api/data/docs
Rate Limit: No strict limit, but be reasonable (~10 req/sec recommended)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import aiohttp
from loguru import logger

from .base_client import BaseAPIClient, APIClientConfig


@dataclass
class ChEMBLMolecule:
    """ChEMBL molecule information - complete API response."""
    chembl_id: str
    pref_name: Optional[str] = None
    molecule_type: Optional[str] = None
    max_phase: Optional[str] = None  # "0"-"4", 4 = approved drug
    structure_type: Optional[str] = None

    # Structure
    canonical_smiles: Optional[str] = None
    standard_inchi: Optional[str] = None
    inchi_key: Optional[str] = None
    molfile: Optional[str] = None

    # Properties (from molecule_properties)
    molecular_weight: Optional[float] = None
    mw_freebase: Optional[float] = None
    alogp: Optional[float] = None
    psa: Optional[float] = None
    hbd: Optional[int] = None
    hba: Optional[int] = None
    heavy_atom_count: Optional[int] = None
    rtb: Optional[int] = None  # Rotatable bonds
    num_ro5_violations: Optional[int] = None
    aromatic_rings: Optional[int] = None
    qed_weighted: Optional[float] = None
    np_likeness_score: Optional[float] = None
    full_molformula: Optional[str] = None
    ro3_pass: Optional[str] = None

    # Clinical/Development flags
    first_approval: Optional[int] = None  # Year
    withdrawn_flag: bool = False
    first_in_class: bool = False
    prodrug: bool = False
    natural_product: bool = False
    therapeutic_flag: bool = False
    dosed_ingredient: bool = False
    orphan: bool = False
    chemical_probe: bool = False
    inorganic_flag: bool = False
    polymer_flag: bool = False

    # Administration routes
    oral: bool = False
    parenteral: bool = False
    topical: bool = False

    # Safety
    black_box_warning: bool = False

    # Availability
    availability_type: Optional[int] = None
    chirality: Optional[int] = None

    # USAN
    usan_stem: Optional[str] = None
    usan_stem_definition: Optional[str] = None
    usan_substem: Optional[str] = None
    usan_year: Optional[int] = None

    # Classifications
    atc_classifications: List[str] = field(default_factory=list)
    molecule_synonyms: List[Dict[str, str]] = field(default_factory=list)

    # Cross-references
    cross_references: List[Dict[str, str]] = field(default_factory=list)
    drugbank_id: Optional[str] = None
    pubchem_cid: Optional[str] = None

    # Hierarchy
    parent_chembl_id: Optional[str] = None
    active_chembl_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chembl_id": self.chembl_id,
            "pref_name": self.pref_name,
            "molecule_type": self.molecule_type,
            "max_phase": self.max_phase,
            "structure_type": self.structure_type,
            "canonical_smiles": self.canonical_smiles,
            "standard_inchi": self.standard_inchi,
            "inchi_key": self.inchi_key,
            "molecular_weight": self.molecular_weight,
            "mw_freebase": self.mw_freebase,
            "alogp": self.alogp,
            "psa": self.psa,
            "hbd": self.hbd,
            "hba": self.hba,
            "heavy_atom_count": self.heavy_atom_count,
            "rtb": self.rtb,
            "num_ro5_violations": self.num_ro5_violations,
            "aromatic_rings": self.aromatic_rings,
            "qed_weighted": self.qed_weighted,
            "np_likeness_score": self.np_likeness_score,
            "full_molformula": self.full_molformula,
            "first_approval": self.first_approval,
            "withdrawn_flag": self.withdrawn_flag,
            "first_in_class": self.first_in_class,
            "prodrug": self.prodrug,
            "natural_product": self.natural_product,
            "therapeutic_flag": self.therapeutic_flag,
            "oral": self.oral,
            "parenteral": self.parenteral,
            "topical": self.topical,
            "black_box_warning": self.black_box_warning,
            "drugbank_id": self.drugbank_id,
            "pubchem_cid": self.pubchem_cid,
            "atc_classifications": self.atc_classifications,
            "molecule_synonyms": self.molecule_synonyms,
            "cross_references": self.cross_references,
            "parent_chembl_id": self.parent_chembl_id,
        }


@dataclass
class ChEMBLTarget:
    """ChEMBL target information."""
    target_chembl_id: str
    pref_name: Optional[str] = None
    target_type: Optional[str] = None
    organism: Optional[str] = None

    # Components (for protein targets)
    target_components: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_chembl_id": self.target_chembl_id,
            "pref_name": self.pref_name,
            "target_type": self.target_type,
            "organism": self.organism,
            "target_components": self.target_components,
        }


@dataclass
class ChEMBLActivity:
    """ChEMBL activity/binding data."""
    activity_id: int
    molecule_chembl_id: str
    target_chembl_id: str

    # Activity data
    standard_type: Optional[str] = None  # IC50, Ki, Kd, EC50, etc.
    standard_value: Optional[float] = None
    standard_units: Optional[str] = None

    # Assay info
    assay_chembl_id: Optional[str] = None
    assay_type: Optional[str] = None

    # Target info
    target_pref_name: Optional[str] = None
    target_organism: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "activity_id": self.activity_id,
            "molecule_chembl_id": self.molecule_chembl_id,
            "target_chembl_id": self.target_chembl_id,
            "standard_type": self.standard_type,
            "standard_value": self.standard_value,
            "standard_units": self.standard_units,
            "assay_chembl_id": self.assay_chembl_id,
            "assay_type": self.assay_type,
            "target_pref_name": self.target_pref_name,
            "target_organism": self.target_organism,
        }


@dataclass
class ChEMBLMechanism:
    """ChEMBL drug mechanism of action - complete API response."""
    molecule_chembl_id: str
    parent_molecule_chembl_id: Optional[str] = None
    mechanism_of_action: Optional[str] = None
    target_chembl_id: Optional[str] = None
    target_name: Optional[str] = None
    action_type: Optional[str] = None  # INHIBITOR, AGONIST, etc.

    # Additional details
    mec_id: Optional[int] = None
    max_phase: Optional[int] = None
    record_id: Optional[int] = None
    site_id: Optional[int] = None

    # Flags
    direct_interaction: bool = False
    disease_efficacy: bool = False
    molecular_mechanism: bool = False

    # Comments
    binding_site_comment: Optional[str] = None
    mechanism_comment: Optional[str] = None
    selectivity_comment: Optional[str] = None
    variant_sequence: Optional[str] = None

    # References
    mechanism_refs: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "molecule_chembl_id": self.molecule_chembl_id,
            "parent_molecule_chembl_id": self.parent_molecule_chembl_id,
            "mechanism_of_action": self.mechanism_of_action,
            "target_chembl_id": self.target_chembl_id,
            "target_name": self.target_name,
            "action_type": self.action_type,
            "mec_id": self.mec_id,
            "max_phase": self.max_phase,
            "direct_interaction": self.direct_interaction,
            "disease_efficacy": self.disease_efficacy,
            "molecular_mechanism": self.molecular_mechanism,
            "binding_site_comment": self.binding_site_comment,
            "mechanism_comment": self.mechanism_comment,
            "selectivity_comment": self.selectivity_comment,
            "mechanism_refs": self.mechanism_refs,
        }


class ChEMBLClient(BaseAPIClient):
    """
    Client for ChEMBL REST API.

    API Documentation: https://www.ebi.ac.uk/chembl/api/data/docs
    """

    BASE_URL = "https://www.ebi.ac.uk/chembl/api/data"

    def __init__(self, cache_ttl: int = 86400):
        config = APIClientConfig(
            base_url=self.BASE_URL,
            requests_per_second=10.0,  # 10 requests per second
            cache_ttl=cache_ttl,
        )
        super().__init__(config)

    async def health_check(self) -> bool:
        """
        Check if the ChEMBL API is healthy and accessible.

        Returns:
            True if API is healthy, False otherwise
        """
        try:
            # Try to fetch status/statistics endpoint
            data = await self._make_request("status")
            return data is not None
        except Exception as e:
            logger.warning(f"ChEMBL API health check failed: {e}")
            return False

    async def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Make API request to ChEMBL."""
        url = f"{self.BASE_URL}/{endpoint}.json"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30),
                    headers={"Accept": "application/json"},
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 404:
                        return None
                    else:
                        logger.warning(f"ChEMBL API returned {response.status} for {endpoint}")
                        return None
        except Exception as e:
            logger.error(f"ChEMBL API request failed: {e}")
            return None

    async def get_molecule(self, chembl_id: str) -> Optional[ChEMBLMolecule]:
        """
        Get molecule by ChEMBL ID.

        Args:
            chembl_id: ChEMBL molecule ID (e.g., CHEMBL25)

        Returns:
            ChEMBLMolecule or None
        """
        data = await self._make_request(f"molecule/{chembl_id}")
        if not data:
            return None

        return self._parse_molecule(data)

    async def search_molecules(
        self,
        query: str,
        limit: int = 10,
    ) -> List[ChEMBLMolecule]:
        """
        Search for molecules by name.

        Args:
            query: Drug/molecule name to search
            limit: Maximum results to return

        Returns:
            List of matching molecules
        """
        molecules = []

        # Search by pref_name (exact and contains)
        params = {
            "pref_name__icontains": query,
            "limit": limit,
        }

        data = await self._make_request("molecule", params)
        if data and "molecules" in data:
            for mol_data in data["molecules"][:limit]:
                mol = self._parse_molecule(mol_data)
                if mol:
                    molecules.append(mol)

        # If no results, try synonyms
        if not molecules:
            params = {
                "molecule_synonyms__molecule_synonym__icontains": query,
                "limit": limit,
            }
            data = await self._make_request("molecule", params)
            if data and "molecules" in data:
                for mol_data in data["molecules"][:limit]:
                    mol = self._parse_molecule(mol_data)
                    if mol:
                        molecules.append(mol)

        return molecules

    async def get_activities(
        self,
        molecule_chembl_id: str,
        limit: int = 50,
    ) -> List[ChEMBLActivity]:
        """
        Get bioactivity data for a molecule.

        Args:
            molecule_chembl_id: ChEMBL molecule ID
            limit: Maximum activities to return

        Returns:
            List of activity records
        """
        activities = []

        params = {
            "molecule_chembl_id": molecule_chembl_id,
            "limit": limit,
        }

        data = await self._make_request("activity", params)
        if data and "activities" in data:
            for act_data in data["activities"]:
                activity = ChEMBLActivity(
                    activity_id=act_data.get("activity_id", 0),
                    molecule_chembl_id=act_data.get("molecule_chembl_id", ""),
                    target_chembl_id=act_data.get("target_chembl_id", ""),
                    standard_type=act_data.get("standard_type"),
                    standard_value=act_data.get("standard_value"),
                    standard_units=act_data.get("standard_units"),
                    assay_chembl_id=act_data.get("assay_chembl_id"),
                    assay_type=act_data.get("assay_type"),
                    target_pref_name=act_data.get("target_pref_name"),
                    target_organism=act_data.get("target_organism"),
                )
                activities.append(activity)

        return activities

    async def get_mechanisms(
        self,
        molecule_chembl_id: str,
    ) -> List[ChEMBLMechanism]:
        """
        Get drug mechanisms of action with all available fields.

        Args:
            molecule_chembl_id: ChEMBL molecule ID

        Returns:
            List of mechanism records
        """
        mechanisms = []

        params = {
            "molecule_chembl_id": molecule_chembl_id,
        }

        data = await self._make_request("mechanism", params)
        if data and "mechanisms" in data:
            for mech_data in data["mechanisms"]:
                # Parse mechanism references
                mech_refs = []
                for ref in mech_data.get("mechanism_refs") or []:
                    mech_refs.append({
                        "ref_type": ref.get("ref_type"),
                        "ref_id": ref.get("ref_id"),
                        "ref_url": ref.get("ref_url"),
                    })

                mechanism = ChEMBLMechanism(
                    molecule_chembl_id=mech_data.get("molecule_chembl_id", ""),
                    parent_molecule_chembl_id=mech_data.get("parent_molecule_chembl_id"),
                    mechanism_of_action=mech_data.get("mechanism_of_action"),
                    target_chembl_id=mech_data.get("target_chembl_id"),
                    target_name=mech_data.get("target_pref_name"),
                    action_type=mech_data.get("action_type"),
                    mec_id=mech_data.get("mec_id"),
                    max_phase=mech_data.get("max_phase"),
                    record_id=mech_data.get("record_id"),
                    site_id=mech_data.get("site_id"),
                    direct_interaction=bool(mech_data.get("direct_interaction")),
                    disease_efficacy=bool(mech_data.get("disease_efficacy")),
                    molecular_mechanism=bool(mech_data.get("molecular_mechanism")),
                    binding_site_comment=mech_data.get("binding_site_comment"),
                    mechanism_comment=mech_data.get("mechanism_comment"),
                    selectivity_comment=mech_data.get("selectivity_comment"),
                    variant_sequence=mech_data.get("variant_sequence"),
                    mechanism_refs=mech_refs,
                )
                mechanisms.append(mechanism)

        return mechanisms

    async def get_target(self, target_chembl_id: str) -> Optional[ChEMBLTarget]:
        """
        Get target by ChEMBL ID.

        Args:
            target_chembl_id: ChEMBL target ID

        Returns:
            ChEMBLTarget or None
        """
        data = await self._make_request(f"target/{target_chembl_id}")
        if not data:
            return None

        components = []
        if "target_components" in data:
            for comp in data["target_components"]:
                components.append({
                    "accession": comp.get("accession"),
                    "component_type": comp.get("component_type"),
                    "description": comp.get("component_description"),
                })

        return ChEMBLTarget(
            target_chembl_id=data.get("target_chembl_id", ""),
            pref_name=data.get("pref_name"),
            target_type=data.get("target_type"),
            organism=data.get("organism"),
            target_components=components,
        )

    async def search_by_inchi_key(self, inchi_key: str) -> Optional[ChEMBLMolecule]:
        """
        Search for molecule by InChI Key.

        Args:
            inchi_key: Standard InChI Key

        Returns:
            ChEMBLMolecule or None
        """
        params = {
            "molecule_structures__standard_inchi_key": inchi_key,
            "limit": 1,
        }

        data = await self._make_request("molecule", params)
        if data and "molecules" in data and data["molecules"]:
            return self._parse_molecule(data["molecules"][0])

        return None

    def _parse_molecule(self, data: Dict[str, Any]) -> Optional[ChEMBLMolecule]:
        """Parse API response into ChEMBLMolecule with all available fields."""
        if not data:
            return None

        # Extract nested data
        structures = data.get("molecule_structures") or {}
        properties = data.get("molecule_properties") or {}
        hierarchy = data.get("molecule_hierarchy") or {}

        # Extract cross-references
        cross_refs = data.get("cross_references") or []
        drugbank_id = None
        pubchem_cid = None
        for ref in cross_refs:
            if ref.get("xref_src") == "DrugBank":
                drugbank_id = ref.get("xref_id")
            elif ref.get("xref_src") == "PubChem":
                pubchem_cid = ref.get("xref_id")

        # Extract synonyms
        synonyms = []
        for syn in data.get("molecule_synonyms") or []:
            synonyms.append({
                "synonym": syn.get("molecule_synonym"),
                "syn_type": syn.get("syn_type"),
            })

        # Parse numeric properties (API returns strings for some)
        def safe_float(val):
            if val is None:
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        def safe_int(val):
            if val is None:
                return None
            try:
                return int(val)
            except (ValueError, TypeError):
                return None

        return ChEMBLMolecule(
            chembl_id=data.get("molecule_chembl_id", ""),
            pref_name=data.get("pref_name"),
            molecule_type=data.get("molecule_type"),
            max_phase=str(data.get("max_phase")) if data.get("max_phase") is not None else None,
            structure_type=data.get("structure_type"),
            # Structures
            canonical_smiles=structures.get("canonical_smiles"),
            standard_inchi=structures.get("standard_inchi"),
            inchi_key=structures.get("standard_inchi_key"),
            molfile=structures.get("molfile"),
            # Properties
            molecular_weight=safe_float(properties.get("full_mwt")),
            mw_freebase=safe_float(properties.get("mw_freebase")),
            alogp=safe_float(properties.get("alogp")),
            psa=safe_float(properties.get("psa")),
            hbd=safe_int(properties.get("hbd")),
            hba=safe_int(properties.get("hba")),
            heavy_atom_count=safe_int(properties.get("heavy_atoms")),
            rtb=safe_int(properties.get("rtb")),
            num_ro5_violations=safe_int(properties.get("num_ro5_violations")),
            aromatic_rings=safe_int(properties.get("aromatic_rings")),
            qed_weighted=safe_float(properties.get("qed_weighted")),
            np_likeness_score=safe_float(properties.get("np_likeness_score")),
            full_molformula=properties.get("full_molformula"),
            ro3_pass=properties.get("ro3_pass"),
            # Clinical flags
            first_approval=safe_int(data.get("first_approval")),
            withdrawn_flag=bool(data.get("withdrawn_flag")),
            first_in_class=bool(data.get("first_in_class")),
            prodrug=bool(data.get("prodrug")),
            natural_product=bool(data.get("natural_product")),
            therapeutic_flag=bool(data.get("therapeutic_flag")),
            dosed_ingredient=bool(data.get("dosed_ingredient")),
            orphan=bool(data.get("orphan")),
            chemical_probe=bool(data.get("chemical_probe")),
            inorganic_flag=bool(data.get("inorganic_flag")),
            polymer_flag=bool(data.get("polymer_flag")),
            # Administration
            oral=bool(data.get("oral")),
            parenteral=bool(data.get("parenteral")),
            topical=bool(data.get("topical")),
            # Safety
            black_box_warning=bool(data.get("black_box_warning")),
            # Availability
            availability_type=safe_int(data.get("availability_type")),
            chirality=safe_int(data.get("chirality")),
            # USAN
            usan_stem=data.get("usan_stem"),
            usan_stem_definition=data.get("usan_stem_definition"),
            usan_substem=data.get("usan_substem"),
            usan_year=safe_int(data.get("usan_year")),
            # Classifications
            atc_classifications=data.get("atc_classifications") or [],
            molecule_synonyms=synonyms,
            # Cross-refs
            cross_references=[{"src": r.get("xref_src"), "id": r.get("xref_id"), "name": r.get("xref_name")} for r in cross_refs],
            drugbank_id=drugbank_id,
            pubchem_cid=pubchem_cid,
            # Hierarchy
            parent_chembl_id=hierarchy.get("parent_chembl_id"),
            active_chembl_id=hierarchy.get("active_chembl_id"),
        )

    async def get_drug_data(
        self,
        drug_name: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive drug data from ChEMBL.

        This is a convenience method that fetches molecule info,
        mechanisms, and top activities.

        Args:
            drug_name: Drug name to search

        Returns:
            Dictionary with molecule, mechanisms, and activities
        """
        # Search for the molecule
        molecules = await self.search_molecules(drug_name, limit=1)
        if not molecules:
            return None

        molecule = molecules[0]

        # Get mechanisms and activities
        mechanisms = await self.get_mechanisms(molecule.chembl_id)
        activities = await self.get_activities(molecule.chembl_id, limit=20)

        return {
            "molecule": molecule.to_dict(),
            "mechanisms": [m.to_dict() for m in mechanisms],
            "activities": [a.to_dict() for a in activities],
        }
