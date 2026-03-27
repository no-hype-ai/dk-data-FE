"""
Gold Molecule Profile Models

Pydantic models for the Gold molecule_profile view.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class MoleculeProfileBase(BaseModel):
    """Base molecule profile fields."""
    inchi_key: Optional[str] = None
    canonical_name: str
    canonical_smiles: Optional[str] = None
    inchi: Optional[str] = None
    molecular_formula: Optional[str] = None
    molecular_weight: Optional[float] = None
    molecule_type: Optional[str] = None
    therapeutic_areas: Optional[List[str]] = None
    mechanism_of_action: Optional[str] = None
    development_status: Optional[str] = None
    max_phase: Optional[int] = None
    first_approval_year: Optional[int] = None
    approval_date: Optional[date] = None


class MoleculeProfile(MoleculeProfileBase):
    """Full molecule profile from Gold layer."""
    model_config = ConfigDict(from_attributes=True)

    molecule_id: UUID
    resolution_confidence: float = 1.0
    data_sources: Optional[List[str]] = None
    primary_source: Optional[str] = None

    # Cross-references
    drugbank_id: Optional[str] = None
    molecule_chembl_id: Optional[str] = None
    pubchem_cid: Optional[int] = None
    unii: Optional[str] = None
    cas_number: Optional[str] = None
    rxcui: Optional[str] = None

    # Aliases
    aliases: Optional[List[str]] = None

    # Trial counts
    total_trials: int = 0
    active_trials: int = 0
    phase_3_trials: int = 0
    phase_2_trials: int = 0
    phase_1_trials: int = 0

    # Safety summary
    total_adverse_reports: int = 0
    serious_adverse_reports: int = 0
    death_reports: int = 0
    first_adverse_report: Optional[date] = None
    last_adverse_report: Optional[date] = None
    top_adverse_events: Optional[List[Dict[str, Any]]] = None

    # Label info
    has_boxed_warning: bool = False
    primary_brand_name: Optional[str] = None
    primary_indication: Optional[str] = None

    # Related entity counts
    target_count: int = 0
    publication_count: int = 0
    patent_count: int = 0
    earliest_patent_expiry: Optional[date] = None

    # Lifecycle
    lifecycle_stage: Optional[str] = None

    # Timestamps
    created_at: datetime
    updated_at: datetime
    profile_generated_at: Optional[datetime] = None


class MoleculeProfileSummary(BaseModel):
    """Summary view of molecule profile."""
    molecule_id: UUID
    inchi_key: Optional[str]
    canonical_name: str
    development_status: Optional[str]
    lifecycle_stage: Optional[str]
    total_trials: int
    active_trials: int
    has_boxed_warning: bool
    data_sources: Optional[List[str]]


class CompetitiveLandscape(BaseModel):
    """Competitive landscape view."""
    model_config = ConfigDict(from_attributes=True)

    molecule_id: UUID
    inchi_key: Optional[str]
    canonical_name: str
    therapeutic_areas: Optional[List[str]]
    mechanism_of_action: Optional[str]
    development_status: Optional[str]
    max_phase: Optional[int]
    active_trials: int
    phase_distribution: Optional[Dict[str, int]]
    indications: Optional[List[str]]
    sponsors: Optional[List[str]]


class CompanyPipeline(BaseModel):
    """Company pipeline view."""
    model_config = ConfigDict(from_attributes=True)

    company: str
    molecule_id: UUID
    inchi_key: Optional[str]
    canonical_name: str
    development_status: Optional[str]
    phase: Optional[str]
    trial_status: Optional[str]
    indications: Optional[List[str]]
    trial_count: int
    latest_trial_start: Optional[date]


class LifecycleStage(BaseModel):
    """Lifecycle stage view."""
    model_config = ConfigDict(from_attributes=True)

    molecule_id: UUID
    inchi_key: Optional[str]
    canonical_name: str
    lifecycle_stage: str
    max_phase: Optional[int]
    first_approval_year: Optional[int]
    approval_date: Optional[date]
    confidence: float

    # Evidence counts
    trial_evidence_count: int
    label_evidence_count: int
    safety_evidence_count: int
    publication_evidence_count: int

    data_sources: Optional[List[str]]
    stage_detected_at: datetime


class LifecycleEvidence(BaseModel):
    """Evidence supporting lifecycle stage."""
    model_config = ConfigDict(from_attributes=True)

    molecule_id: UUID
    inchi_key: Optional[str]
    canonical_name: str
    evidence_type: str  # clinical_trial, drug_label
    evidence_id: str
    evidence_title: Optional[str]
    evidence_detail: Optional[str]
    evidence_status: Optional[str]
    evidence_source: Optional[str]
    evidence_date: Optional[datetime]
    evidence_url: Optional[str]
