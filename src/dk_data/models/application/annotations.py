"""
User Annotations Models

Pydantic models for user annotations on molecules.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class AnnotationType(str, Enum):
    """Type of annotation."""
    NOTE = "note"
    TAG = "tag"
    RATING = "rating"
    ALERT = "alert"
    LINK = "link"
    CUSTOM = "custom"


class UserAnnotationBase(BaseModel):
    """Base annotation fields."""
    molecule_id: UUID
    annotation_type: AnnotationType
    content: str = Field(..., max_length=5000)
    metadata: Optional[Dict[str, Any]] = None
    is_private: bool = True


class UserAnnotationCreate(UserAnnotationBase):
    """Model for creating an annotation."""
    pass


class UserAnnotationUpdate(BaseModel):
    """Model for updating an annotation."""
    content: Optional[str] = Field(default=None, max_length=5000)
    metadata: Optional[Dict[str, Any]] = None
    is_private: Optional[bool] = None


class UserAnnotation(UserAnnotationBase):
    """Full annotation model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


class UserAnnotationWithMolecule(UserAnnotation):
    """Annotation with molecule info."""
    model_config = ConfigDict(from_attributes=True)

    # From mol_silver.molecules
    inchi_key: Optional[str] = None
    canonical_name: str


class AnnotationSummary(BaseModel):
    """Summary of annotations for a molecule."""
    molecule_id: UUID
    total_annotations: int = 0
    by_type: Dict[str, int] = Field(default_factory=dict)
    latest_annotation: Optional[datetime] = None
    tags: List[str] = Field(default_factory=list)
