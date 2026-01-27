"""
Silver Patents Model

Normalized patent data.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime, date
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


class PatentStatus(str, Enum):
    """Patent status."""
    ACTIVE = "active"
    EXPIRED = "expired"
    PENDING = "pending"
    ABANDONED = "abandoned"


class PatentBase(BaseModel):
    """Base patent fields."""
    molecule_id: Optional[UUID] = None
    
    # Identifiers
    patent_number: str
    application_number: Optional[str] = None
    
    # Title and content
    title: str
    abstract: Optional[str] = None
    
    # Dates
    filing_date: Optional[date] = None
    grant_date: Optional[date] = None
    expiry_date: Optional[date] = None
    
    # Parties
    assignee: Optional[str] = None
    assignee_normalized: Optional[str] = None
    inventors: Optional[List[str]] = None
    
    # Classification
    patent_type: Optional[str] = None
    cpc_codes: Optional[List[str]] = None
    ipc_codes: Optional[List[str]] = None
    
    # Status
    status: PatentStatus = PatentStatus.ACTIVE
    
    # Extensions
    pediatric_extension: Optional[bool] = None
    extension_days: Optional[int] = None
    
    # Cross-references
    related_patents: Optional[List[str]] = None
    
    # Source
    source: str = "orange_book"


class PatentCreate(PatentBase):
    """Model for creating a patent."""
    pass


class Patent(PatentBase):
    """Full patent model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class PatentSummary(BaseModel):
    """Summary view of patent."""
    id: UUID
    patent_number: str
    title: str
    assignee: Optional[str]
    grant_date: Optional[date]
    expiry_date: Optional[date]
    status: PatentStatus


class MoleculePatentSummary(BaseModel):
    """Patent summary for a molecule."""
    molecule_id: UUID
    total_patents: int = 0
    active_patents: int = 0
    earliest_expiry: Optional[date] = None
    latest_expiry: Optional[date] = None
    primary_assignees: List[str] = Field(default_factory=list)
