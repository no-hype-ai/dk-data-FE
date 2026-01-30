"""
Silver Clinical Trials Models

Pydantic models for the Silver clinical_trials table.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from uuid import UUID
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class TrialPhase(str, Enum):
    """Clinical trial phase."""
    EARLY_PHASE_1 = "Early Phase 1"
    PHASE_1 = "Phase 1"
    PHASE_1_2 = "Phase 1/Phase 2"
    PHASE_2 = "Phase 2"
    PHASE_2_3 = "Phase 2/Phase 3"
    PHASE_3 = "Phase 3"
    PHASE_4 = "Phase 4"
    NOT_APPLICABLE = "Not Applicable"


class TrialStatus(str, Enum):
    """Clinical trial status."""
    NOT_YET_RECRUITING = "Not yet recruiting"
    RECRUITING = "Recruiting"
    ENROLLING_BY_INVITATION = "Enrolling by invitation"
    ACTIVE_NOT_RECRUITING = "Active, not recruiting"
    SUSPENDED = "Suspended"
    TERMINATED = "Terminated"
    COMPLETED = "Completed"
    WITHDRAWN = "Withdrawn"
    UNKNOWN = "Unknown status"


class StudyType(str, Enum):
    """Clinical study type."""
    INTERVENTIONAL = "Interventional"
    OBSERVATIONAL = "Observational"
    EXPANDED_ACCESS = "Expanded Access"


class ClinicalTrialBase(BaseModel):
    """Base clinical trial fields."""
    nct_id: str = Field(..., pattern=r'^NCT\d{8}$')
    org_study_id: Optional[str] = None
    title: str
    brief_summary: Optional[str] = None
    phase: Optional[TrialPhase] = None
    study_type: Optional[StudyType] = None
    status: Optional[TrialStatus] = None
    start_date: Optional[date] = None
    completion_date: Optional[date] = None
    primary_completion_date: Optional[date] = None
    sponsor: Optional[str] = None
    sponsor_type: Optional[str] = None


class ClinicalTrialCreate(ClinicalTrialBase):
    """Model for creating a clinical trial."""
    molecule_id: Optional[UUID] = None
    collaborators: Optional[List[Dict[str, str]]] = None
    allocation: Optional[str] = None
    intervention_model: Optional[str] = None
    masking: Optional[str] = None
    enrollment: Optional[int] = None
    eligibility_criteria: Optional[str] = None
    minimum_age: Optional[str] = None
    maximum_age: Optional[str] = None
    sex: Optional[str] = None
    conditions: Optional[List[str]] = None
    interventions: Optional[List[Dict[str, Any]]] = None
    primary_outcomes: Optional[List[Dict[str, Any]]] = None
    secondary_outcomes: Optional[List[Dict[str, Any]]] = None
    locations: Optional[List[Dict[str, Any]]] = None
    countries: Optional[List[str]] = None


class ClinicalTrial(ClinicalTrialBase):
    """Full clinical trial model from database."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    molecule_id: Optional[UUID] = None
    collaborators: Optional[List[Dict[str, str]]] = None
    allocation: Optional[str] = None
    intervention_model: Optional[str] = None
    masking: Optional[str] = None
    enrollment: Optional[int] = None
    eligibility_criteria: Optional[str] = None
    minimum_age: Optional[str] = None
    maximum_age: Optional[str] = None
    sex: Optional[str] = None
    conditions: Optional[List[str]] = None
    interventions: Optional[List[Dict[str, Any]]] = None
    primary_outcomes: Optional[List[Dict[str, Any]]] = None
    secondary_outcomes: Optional[List[Dict[str, Any]]] = None
    locations: Optional[List[Dict[str, Any]]] = None
    countries: Optional[List[str]] = None
    source: str = "clinicaltrials_gov"
    source_updated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ClinicalTrialSummary(BaseModel):
    """Summary view of a clinical trial."""
    id: UUID
    nct_id: str
    title: str
    phase: Optional[str]
    status: Optional[str]
    sponsor: Optional[str]
    start_date: Optional[date]
    molecule_name: Optional[str] = None


class TrialCountByPhase(BaseModel):
    """Trial counts grouped by phase."""
    phase: str
    count: int
    active_count: int
