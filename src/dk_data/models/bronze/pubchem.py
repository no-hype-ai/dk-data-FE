"""
Bronze PubChem Models

Typed extraction from raw_pubchem JSON.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class BronzePubChemCompoundBase(BaseModel):
    """Base fields for Bronze PubChem compound."""
    cid: int = Field(..., description="PubChem Compound ID")
    
    # Names
    iupac_name: Optional[str] = None
    title: Optional[str] = None
    synonyms: Optional[List[str]] = None
    
    # Structure
    canonical_smiles: Optional[str] = None
    isomeric_smiles: Optional[str] = None
    inchi: Optional[str] = None
    inchikey: Optional[str] = None
    molecular_formula: Optional[str] = None
    
    # Properties
    molecular_weight: Optional[float] = None
    exact_mass: Optional[float] = None
    monoisotopic_mass: Optional[float] = None
    xlogp: Optional[float] = None
    tpsa: Optional[float] = None
    complexity: Optional[float] = None
    charge: Optional[int] = None
    
    # Counts
    h_bond_donor_count: Optional[int] = None
    h_bond_acceptor_count: Optional[int] = None
    rotatable_bond_count: Optional[int] = None
    heavy_atom_count: Optional[int] = None
    atom_stereo_count: Optional[int] = None
    defined_atom_stereo_count: Optional[int] = None
    undefined_atom_stereo_count: Optional[int] = None
    bond_stereo_count: Optional[int] = None
    covalent_unit_count: Optional[int] = None
    
    # Cross-references
    cas_rn: Optional[str] = None
    chembl_id: Optional[str] = None
    drugbank_id: Optional[str] = None
    unii: Optional[str] = None
    
    # Additional data
    pharmacology: Optional[Dict[str, Any]] = None
    drug_indications: Optional[List[str]] = None
    atc_codes: Optional[List[str]] = None


class BronzePubChemCompound(BronzePubChemCompoundBase):
    """Full Bronze PubChem compound model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_id: UUID
    processed_at: datetime
    created_at: datetime
    updated_at: datetime
    extraction_version: str = "1.0"
