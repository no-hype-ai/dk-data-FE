"""
Tracked Molecules Models

Pydantic models for user-tracked molecules.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class TrackingStatus(str, Enum):
    """Status of molecule tracking."""
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class TrackedMoleculeBase(BaseModel):
    """Base tracked molecule fields."""
    molecule_id: UUID
    tracking_reason: Optional[str] = None
    priority: int = Field(default=0, ge=0, le=10)
    tags: Optional[List[str]] = None
    notification_settings: Optional[Dict[str, Any]] = None


class TrackedMoleculeCreate(TrackedMoleculeBase):
    """Model for creating a tracked molecule."""
    pass


class TrackedMoleculeUpdate(BaseModel):
    """Model for updating a tracked molecule."""
    tracking_reason: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=0, le=10)
    tags: Optional[List[str]] = None
    notification_settings: Optional[Dict[str, Any]] = None
    status: Optional[TrackingStatus] = None


class TrackedMolecule(TrackedMoleculeBase):
    """Full tracked molecule model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    status: TrackingStatus = TrackingStatus.ACTIVE
    created_at: datetime
    updated_at: datetime
    last_notified_at: Optional[datetime] = None


class TrackedMoleculeWithDetails(TrackedMolecule):
    """Tracked molecule with molecule details from Silver layer."""
    model_config = ConfigDict(from_attributes=True)

    # From mol_silver.molecules
    inchi_key: Optional[str] = None
    canonical_name: str
    canonical_smiles: Optional[str] = None
    development_status: Optional[str] = None
    max_phase: Optional[int] = None
    therapeutic_areas: Optional[List[str]] = None

    # Counts
    active_trials: int = 0
    total_trials: int = 0
    publication_count: int = 0

    # Recent changes
    recent_changes: Optional[List[Dict[str, Any]]] = None
    has_unread_updates: bool = False


class TrackedMoleculeStats(BaseModel):
    """Statistics about user's tracked molecules."""
    total_tracked: int = 0
    active_tracked: int = 0
    by_status: Dict[str, int] = Field(default_factory=dict)
    by_development_stage: Dict[str, int] = Field(default_factory=dict)
    by_therapeutic_area: Dict[str, int] = Field(default_factory=dict)
    molecules_with_updates: int = 0
