"""
Bronze OpenFDA FAERS Models

Typed extraction from raw_openfda_faers JSON.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class BronzeAdverseEventBase(BaseModel):
    """Base fields for Bronze adverse event."""
    safety_report_id: str = Field(..., description="FAERS safety report ID")
    safety_report_version: Optional[int] = None
    
    # Report Info
    receive_date: Optional[date] = None
    receipt_date: Optional[date] = None
    report_type: Optional[str] = None
    serious: Optional[int] = None
    
    # Seriousness criteria
    serious_death: Optional[int] = None
    serious_disabling: Optional[int] = None
    serious_hospitalization: Optional[int] = None
    serious_lifethreatening: Optional[int] = None
    serious_other: Optional[int] = None
    
    # Patient
    patient_age: Optional[float] = None
    patient_age_unit: Optional[str] = None
    patient_sex: Optional[str] = None
    patient_weight: Optional[float] = None
    
    # Drug Info (primary suspect drug)
    drug_name: Optional[str] = None
    drug_characterization: Optional[int] = None  # 1=suspect, 2=concomitant, 3=interacting
    drug_indication: Optional[str] = None
    drug_dosage: Optional[str] = None
    drug_route: Optional[str] = None
    drug_start_date: Optional[date] = None
    drug_end_date: Optional[date] = None
    
    # All drugs in report
    drugs: Optional[List[Dict[str, Any]]] = None
    
    # Reactions
    reactions: Optional[List[Dict[str, Any]]] = None
    reaction_terms: Optional[List[str]] = None
    reaction_outcomes: Optional[List[str]] = None
    
    # OpenFDA enrichment
    openfda: Optional[Dict[str, Any]] = None
    
    # Source
    sender_organization: Optional[str] = None
    occurrence_country: Optional[str] = None


class BronzeAdverseEventCreate(BronzeAdverseEventBase):
    """Model for creating a Bronze adverse event."""
    raw_id: UUID


class BronzeAdverseEvent(BronzeAdverseEventBase):
    """Full Bronze adverse event model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_id: UUID
    processed_at: datetime
    created_at: datetime
    updated_at: datetime

    extraction_version: str = "1.0"
    extraction_errors: Optional[List[str]] = None
