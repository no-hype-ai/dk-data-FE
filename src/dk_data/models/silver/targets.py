"""
Silver Targets Model

Normalized target data from UniProt/ChEMBL.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class TargetBase(BaseModel):
    """Base target fields."""
    # Identifiers
    uniprot_id: Optional[str] = None
    chembl_target_id: Optional[str] = None
    gene_name: Optional[str] = None
    
    # Names
    target_name: str
    target_synonyms: Optional[List[str]] = None
    
    # Classification
    target_type: Optional[str] = None  # SINGLE PROTEIN, PROTEIN COMPLEX, etc.
    organism: Optional[str] = None
    organism_id: Optional[int] = None
    
    # Protein info
    protein_sequence: Optional[str] = None
    sequence_length: Optional[int] = None
    
    # Function
    function_description: Optional[str] = None
    pathway: Optional[List[str]] = None
    subcellular_location: Optional[List[str]] = None
    
    # Disease association
    disease_associations: Optional[List[str]] = None
    
    # Cross-references
    pdb_ids: Optional[List[str]] = None
    ensembl_id: Optional[str] = None
    
    # Source
    source: str = "uniprot"


class TargetCreate(TargetBase):
    """Model for creating a target."""
    pass


class Target(TargetBase):
    """Full target model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class TargetSummary(BaseModel):
    """Summary view of target."""
    id: UUID
    uniprot_id: Optional[str]
    target_name: str
    target_type: Optional[str]
    organism: Optional[str]
    molecule_count: int = 0  # How many molecules target this


class MoleculeTarget(BaseModel):
    """Association between molecule and target."""
    molecule_id: UUID
    target_id: UUID
    activity_count: int = 0
    best_activity_type: Optional[str] = None
    best_activity_value: Optional[float] = None
