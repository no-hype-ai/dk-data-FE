"""
Bronze OpenFDA Labels Models

Typed extraction from raw_openfda_labels JSON.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class BronzeDrugLabelBase(BaseModel):
    """Base fields for Bronze drug label."""
    set_id: str = Field(..., description="SPL Set ID")
    spl_id: Optional[str] = None
    version: Optional[int] = None

    # Product Info
    brand_name: Optional[str] = None
    generic_name: Optional[str] = None
    manufacturer_name: Optional[str] = None
    product_ndc: Optional[List[str]] = None
    product_type: Optional[str] = None
    route: Optional[List[str]] = None
    substance_name: Optional[List[str]] = None

    # Dates
    effective_time: Optional[date] = None
    marketing_start_date: Optional[date] = None

    # Label Sections
    indications_and_usage: Optional[str] = None
    dosage_and_administration: Optional[str] = None
    contraindications: Optional[str] = None
    warnings: Optional[str] = None
    warnings_and_cautions: Optional[str] = None
    boxed_warning: Optional[str] = None
    adverse_reactions: Optional[str] = None
    drug_interactions: Optional[str] = None
    clinical_pharmacology: Optional[str] = None
    mechanism_of_action: Optional[str] = None
    pharmacodynamics: Optional[str] = None
    pharmacokinetics: Optional[str] = None

    # Cross-references
    application_number: Optional[str] = None
    unii: Optional[List[str]] = None
    rxcui: Optional[List[str]] = None
    spl_unclassified_section: Optional[str] = None

    # OpenFDA enrichment
    openfda: Optional[Dict[str, Any]] = None


class BronzeDrugLabelCreate(BronzeDrugLabelBase):
    """Model for creating a Bronze drug label."""
    raw_id: UUID


class BronzeDrugLabel(BronzeDrugLabelBase):
    """Full Bronze drug label model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_id: UUID
    processed_at: datetime
    created_at: datetime
    updated_at: datetime

    extraction_version: str = "1.0"
    extraction_errors: Optional[List[str]] = None
