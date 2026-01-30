"""
Silver Bioactivity Model

Normalized bioactivity data from ChEMBL.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class BioactivityBase(BaseModel):
    """Base bioactivity fields."""
    molecule_id: Optional[UUID] = None
    target_id: Optional[UUID] = None
    
    # Activity identifiers
    chembl_activity_id: Optional[int] = None
    assay_chembl_id: Optional[str] = None
    
    # Activity measurement
    standard_type: Optional[str] = None  # IC50, Ki, EC50, etc.
    standard_relation: Optional[str] = None  # =, <, >, etc.
    standard_value: Optional[float] = None
    standard_units: Optional[str] = None
    pchembl_value: Optional[float] = None  # Normalized -log10(value)
    
    # Assay info
    assay_type: Optional[str] = None  # B=Binding, F=Functional, A=ADMET
    assay_description: Optional[str] = None
    bao_format: Optional[str] = None
    
    # Target info (denormalized for queries)
    target_chembl_id: Optional[str] = None
    target_name: Optional[str] = None
    target_organism: Optional[str] = None
    target_type: Optional[str] = None
    
    # Source
    source: str = "chembl"
    source_id: Optional[str] = None


class BioactivityCreate(BioactivityBase):
    """Model for creating bioactivity record."""
    pass


class Bioactivity(BioactivityBase):
    """Full bioactivity model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class BioactivitySummary(BaseModel):
    """Summary bioactivity for a molecule-target pair."""
    molecule_id: UUID
    target_id: Optional[UUID]
    target_name: Optional[str]
    activity_count: int = 0
    best_pchembl: Optional[float] = None
    best_type: Optional[str] = None
