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
    """Base fields for Bronze ChEMBL molecule."""
    chembl_id: str = Field(..., description="ChEMBL molecule ID")
    
    # Identifiers
    pref_name: Optional[str] = None
    molecule_synonyms: Optional[List[str]] = None
    
    # Structure
    molecule_structures: Optional[Dict[str, Any]] = None
    canonical_smiles: Optional[str] = None
    standard_inchi: Optional[str] = None
    standard_inchi_key: Optional[str] = None
    
    # Properties
    molecule_properties: Optional[Dict[str, Any]] = None
    full_mwt: Optional[float] = None
    molecular_formula: Optional[str] = None
    alogp: Optional[float] = None
    psa: Optional[float] = None
    hba: Optional[int] = None
    hbd: Optional[int] = None
    num_ro5_violations: Optional[int] = None
    
    # Classification
    molecule_type: Optional[str] = None
    structure_type: Optional[str] = None
    therapeutic_flag: Optional[bool] = None
    molecule_hierarchy: Optional[Dict[str, Any]] = None
    
    # Status
    max_phase: Optional[int] = None
    first_approval: Optional[int] = None
    oral: Optional[bool] = None
    parenteral: Optional[bool] = None
    topical: Optional[bool] = None
    
    # Cross-references
    cross_references: Optional[List[Dict[str, Any]]] = None


class BronzeChemblMolecule(BronzeChemblMoleculeBase):
    """Full Bronze ChEMBL molecule model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_id: UUID
    processed_at: datetime
    created_at: datetime
    updated_at: datetime
    extraction_version: str = "1.0"


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
