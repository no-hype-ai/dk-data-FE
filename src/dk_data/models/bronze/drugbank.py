"""
Bronze DrugBank Models

Typed extraction from raw_drugbank JSON/XML.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class BronzeDrugBankDrugBase(BaseModel):
    """Base fields for Bronze DrugBank drug."""
    drugbank_id: str = Field(..., description="Primary DrugBank accession")
    secondary_accession_numbers: Optional[List[str]] = None
    
    # Names
    name: str
    description: Optional[str] = None
    cas_number: Optional[str] = None
    unii: Optional[str] = None
    
    # Synonyms
    synonyms: Optional[List[str]] = None
    international_brands: Optional[List[Dict[str, str]]] = None
    
    # Classification
    drug_type: Optional[str] = None  # small molecule, biotech
    groups: Optional[List[str]] = None  # approved, investigational, etc.
    categories: Optional[List[Dict[str, Any]]] = None
    
    # Chemical
    average_mass: Optional[float] = None
    monoisotopic_mass: Optional[float] = None
    state: Optional[str] = None
    
    # Structure
    smiles: Optional[str] = None
    inchi: Optional[str] = None
    inchikey: Optional[str] = None
    moldb_formula: Optional[str] = None
    
    # Pharmacology
    indication: Optional[str] = None
    pharmacodynamics: Optional[str] = None
    mechanism_of_action: Optional[str] = None
    toxicity: Optional[str] = None
    metabolism: Optional[str] = None
    absorption: Optional[str] = None
    half_life: Optional[str] = None
    protein_binding: Optional[str] = None
    route_of_elimination: Optional[str] = None
    volume_of_distribution: Optional[str] = None
    clearance: Optional[str] = None
    
    # Cross-references
    external_identifiers: Optional[List[Dict[str, str]]] = None
    external_links: Optional[List[Dict[str, str]]] = None
    
    # Targets
    targets: Optional[List[Dict[str, Any]]] = None
    enzymes: Optional[List[Dict[str, Any]]] = None
    carriers: Optional[List[Dict[str, Any]]] = None
    transporters: Optional[List[Dict[str, Any]]] = None
    
    # Products
    products: Optional[List[Dict[str, Any]]] = None
    
    # FDA info
    fda_label: Optional[str] = None
    msds: Optional[str] = None


class BronzeDrugBankDrug(BronzeDrugBankDrugBase):
    """Full Bronze DrugBank drug model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_id: UUID
    processed_at: datetime
    created_at: datetime
    updated_at: datetime
    extraction_version: str = "1.0"


class BronzeDrugBankInteractionBase(BaseModel):
    """Base fields for Bronze DrugBank interaction."""
    drugbank_id: str
    interacting_drugbank_id: str
    interacting_drug_name: Optional[str] = None
    description: Optional[str] = None


class BronzeDrugBankInteraction(BronzeDrugBankInteractionBase):
    """Full Bronze DrugBank interaction model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_id: UUID
    processed_at: datetime
    created_at: datetime
    updated_at: datetime
