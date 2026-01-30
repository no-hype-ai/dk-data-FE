"""
Silver Drug Labels Model

Normalized drug label data from OpenFDA.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime, date
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class DrugLabelBase(BaseModel):
    """Base drug label fields."""
    molecule_id: Optional[UUID] = None
    set_id: str = Field(..., description="SPL Set ID")
    
    # Product Info
    brand_name: Optional[str] = None
    generic_name: Optional[str] = None
    manufacturer_name: Optional[str] = None
    product_type: Optional[str] = None
    route: Optional[List[str]] = None
    
    # Dates
    effective_date: Optional[date] = None
    marketing_start_date: Optional[date] = None
    
    # Key Label Sections
    indications_and_usage: Optional[str] = None
    dosage_and_administration: Optional[str] = None
    contraindications: Optional[str] = None
    warnings: Optional[str] = None
    boxed_warning: Optional[str] = None
    adverse_reactions: Optional[str] = None
    drug_interactions: Optional[str] = None
    mechanism_of_action: Optional[str] = None
    
    # Cross-references
    application_number: Optional[str] = None
    unii: Optional[List[str]] = None
    rxcui: Optional[List[str]] = None
    ndc: Optional[List[str]] = None
    
    # Source
    source: str = "openfda_labels"


class DrugLabelCreate(DrugLabelBase):
    """Model for creating a drug label."""
    pass


class DrugLabel(DrugLabelBase):
    """Full drug label model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    
    # Has boxed warning flag for quick filtering
    has_boxed_warning: bool = False


class DrugLabelSummary(BaseModel):
    """Summary view of drug label."""
    id: UUID
    molecule_id: Optional[UUID]
    set_id: str
    brand_name: Optional[str]
    generic_name: Optional[str]
    has_boxed_warning: bool
    effective_date: Optional[date]
