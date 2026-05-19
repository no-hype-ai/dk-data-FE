"""
Bronze ChEMBL Models

Typed extraction from raw_chembl JSON.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class BronzeChemblMoleculeBase(BaseModel):
    """Base fields for Bronze ChEMBL molecule.

    Field names match the SQL bronze.chembl_molecules output columns exactly.
    Raw ChEMBL API field names are noted in comments where they differ.
    """
    chembl_id: str = Field(..., description="ChEMBL molecule ID (molecule_chembl_id in API)")

    # Identifiers
    pref_name: Optional[str] = None

    # Structure — extracted from molecule_structures nested object in API response
    canonical_smiles: Optional[str] = None
    inchi: Optional[str] = None          # standard_inchi in API
    inchi_key: Optional[str] = None      # standard_inchi_key in API

    # Properties — extracted from molecule_properties nested object in API response
    molecular_formula: Optional[str] = None   # full_molformula in API
    molecular_weight: Optional[float] = None  # full_mwt in API
    alogp: Optional[float] = None
    psa: Optional[float] = None
    hba: Optional[int] = None
    hbd: Optional[int] = None
    num_ro5_violations: Optional[int] = None
    aromatic_rings: Optional[int] = None
    heavy_atoms: Optional[int] = None

    # Classification
    molecule_type: Optional[str] = None
    # Boolean flags: ChEMBL API returns JSON booleans, bronze casts to ::BOOLEAN
    therapeutic_flag: Optional[bool] = None
    prodrug: Optional[bool] = None
    natural_product: Optional[bool] = None

    # Status
    max_phase: Optional[int] = None
    # first_approval: integer year (e.g. 1985), cast to INTEGER in bronze
    first_approval: Optional[int] = None
    indication_class: Optional[str] = None
    usan_stem: Optional[str] = None

    # Synonyms — JSONB array of synonym objects (molecule_synonyms in API)
    # Column name in bronze SQL: synonyms
    synonyms: Optional[List[Dict[str, Any]]] = None

    # Cross-references — JSONB array
    cross_references: Optional[List[Dict[str, Any]]] = None


class BronzeChemblMolecule(BronzeChemblMoleculeBase):
    """Full Bronze ChEMBL molecule model.

    Matches the output schema of bronze.chembl_molecules SQLMesh model.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    # raw_source_id: UUID primary key of the source raw.chembl row
    raw_source_id: Optional[UUID] = None
    raw_json: Optional[Dict[str, Any]] = None
    source: str = "chembl"
    source_updated_at: datetime
    processed_to_silver: bool = False
    created_at: datetime


class BronzeChemblActivityBase(BaseModel):
    """Base fields for Bronze ChEMBL activity."""
    activity_id: int
    molecule_chembl_id: str
    target_chembl_id: Optional[str] = None
    assay_chembl_id: Optional[str] = None
    
    # Activity data
    standard_type: Optional[str] = None
    standard_relation: Optional[str] = None
    standard_value: Optional[float] = None
    standard_units: Optional[str] = None
    pchembl_value: Optional[float] = None
    
    # Target info
    target_pref_name: Optional[str] = None
    target_organism: Optional[str] = None
    target_type: Optional[str] = None
    
    # Assay info
    assay_type: Optional[str] = None
    assay_description: Optional[str] = None
    bao_format: Optional[str] = None


class BronzeChemblActivity(BronzeChemblActivityBase):
    """Full Bronze ChEMBL activity model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_id: UUID
    processed_at: datetime
    created_at: datetime
    updated_at: datetime
