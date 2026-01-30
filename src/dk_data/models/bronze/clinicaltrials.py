"""
Bronze ClinicalTrials.gov Models

Typed extraction from raw_clinicaltrials JSON.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class BronzeClinicalTrialBase(BaseModel):
    """Base fields for Bronze clinical trial."""
    nct_id: str = Field(..., description="NCT identifier")
    title: str
    brief_summary: Optional[str] = None
    detailed_description: Optional[str] = None

    # Study Info
    study_type: Optional[str] = None
    phase: Optional[str] = None
    overall_status: Optional[str] = None
    enrollment: Optional[int] = None
    enrollment_type: Optional[str] = None

    # Dates
    start_date: Optional[date] = None
    completion_date: Optional[date] = None
    primary_completion_date: Optional[date] = None
    first_posted_date: Optional[date] = None
    last_update_posted_date: Optional[date] = None

    # Sponsor
    lead_sponsor: Optional[str] = None
    lead_sponsor_class: Optional[str] = None
    collaborators: Optional[List[str]] = None

    # Conditions and Interventions
    conditions: Optional[List[str]] = None
    interventions: Optional[List[Dict[str, Any]]] = None
    intervention_names: Optional[List[str]] = None
    intervention_types: Optional[List[str]] = None

    # Arms
    arms: Optional[List[Dict[str, Any]]] = None
    arm_count: Optional[int] = None

    # Eligibility
    eligibility_criteria: Optional[str] = None
    gender: Optional[str] = None
    minimum_age: Optional[str] = None
    maximum_age: Optional[str] = None
    healthy_volunteers: Optional[str] = None

    # Locations
    locations: Optional[List[Dict[str, Any]]] = None
    location_countries: Optional[List[str]] = None

    # Outcomes
    primary_outcomes: Optional[List[Dict[str, Any]]] = None
    secondary_outcomes: Optional[List[Dict[str, Any]]] = None

    # Contact
    overall_officials: Optional[List[Dict[str, Any]]] = None
    central_contacts: Optional[List[Dict[str, Any]]] = None


class BronzeClinicalTrialCreate(BronzeClinicalTrialBase):
    """Model for creating a Bronze clinical trial."""
    raw_id: UUID = Field(..., description="Reference to raw_clinicaltrials record")


class BronzeClinicalTrial(BronzeClinicalTrialBase):
    """Full Bronze clinical trial model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_id: UUID
    processed_at: datetime
    created_at: datetime
    updated_at: datetime

    # Extraction metadata
    extraction_version: str = "1.0"
    extraction_errors: Optional[List[str]] = None
