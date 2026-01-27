"""
Onboarding Models

Pydantic models for molecule onboarding workflow.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from uuid import UUID
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class OnboardingStatus(str, Enum):
    """Status of onboarding request."""
    PENDING = "pending"
    RESOLVING = "resolving"
    INGESTING = "ingesting"
    ENRICHING = "enriching"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class IdentifierInput(BaseModel):
    """Input identifier for onboarding."""
    identifier_type: str = Field(
        ...,
        description="Type: inchi_key, drugbank_id, chembl_id, pubchem_cid, cas_number, name"
    )
    identifier_value: str


class OnboardingRequest(BaseModel):
    """Request to onboard a molecule."""
    identifiers: List[IdentifierInput] = Field(
        ...,
        min_length=1,
        description="At least one identifier required"
    )
    priority: int = Field(default=0, ge=0, le=10)
    requested_sources: Optional[List[str]] = Field(
        default=None,
        description="Specific data sources to fetch from"
    )
    skip_enrichment: bool = Field(
        default=False,
        description="Skip additional enrichment after resolution"
    )
    notes: Optional[str] = None


class ResolutionResult(BaseModel):
    """Result of identifier resolution."""
    resolved: bool
    molecule_id: Optional[UUID] = None
    inchi_key: Optional[str] = None
    confidence: float = 0.0
    matched_identifiers: Dict[str, str] = Field(default_factory=dict)
    unmatched_identifiers: List[str] = Field(default_factory=list)
    potential_matches: List[Dict[str, Any]] = Field(default_factory=list)


class OnboardingResponse(BaseModel):
    """Response for onboarding request."""
    model_config = ConfigDict(from_attributes=True)

    request_id: UUID
    status: OnboardingStatus
    resolution_result: Optional[ResolutionResult] = None
    molecule_id: Optional[UUID] = None
    canonical_name: Optional[str] = None
    data_sources_fetched: List[str] = Field(default_factory=list)
    enrichment_complete: bool = False
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class OnboardingAuditLog(BaseModel):
    """Audit log entry for onboarding."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    request_id: UUID
    user_id: UUID
    action: str
    status: OnboardingStatus
    details: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: datetime


class BulkOnboardingRequest(BaseModel):
    """Request to onboard multiple molecules."""
    molecules: List[OnboardingRequest] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of molecules to onboard (max 100)"
    )
    batch_priority: int = Field(default=0, ge=0, le=10)
    continue_on_error: bool = Field(
        default=True,
        description="Continue processing if individual items fail"
    )


class BulkOnboardingResponse(BaseModel):
    """Response for bulk onboarding request."""
    batch_id: UUID
    total_requested: int
    successful: int = 0
    failed: int = 0
    pending: int = 0
    results: List[OnboardingResponse] = Field(default_factory=list)
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime


class OnboardingQueueItem(BaseModel):
    """Item in the onboarding queue."""
    model_config = ConfigDict(from_attributes=True)

    request_id: UUID
    batch_id: Optional[UUID] = None
    user_id: UUID
    identifiers: List[IdentifierInput]
    priority: int
    status: OnboardingStatus
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime
    started_at: Optional[datetime] = None
    last_error: Optional[str] = None
