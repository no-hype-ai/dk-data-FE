"""
Silver Publications Model

Normalized publication data from OpenAlex/PubMed.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class PublicationBase(BaseModel):
    """Base publication fields."""
    # Identifiers
    openalex_id: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    pmcid: Optional[str] = None
    
    # Title and content
    title: str
    abstract: Optional[str] = None
    
    # Publication info
    publication_date: Optional[date] = None
    publication_year: Optional[int] = None
    publication_type: Optional[str] = None
    
    # Journal
    journal_name: Optional[str] = None
    journal_issn: Optional[str] = None
    publisher: Optional[str] = None
    
    # Authors
    authors: Optional[List[str]] = None
    first_author: Optional[str] = None
    last_author: Optional[str] = None
    author_count: Optional[int] = None
    
    # Metrics
    cited_by_count: Optional[int] = None
    is_open_access: Optional[bool] = None
    open_access_url: Optional[str] = None
    
    # Topics/Keywords
    mesh_terms: Optional[List[str]] = None
    keywords: Optional[List[str]] = None
    concepts: Optional[List[Dict[str, Any]]] = None
    
    # Source
    source: str = "openalex"


class PublicationCreate(PublicationBase):
    """Model for creating a publication."""
    pass


class Publication(PublicationBase):
    """Full publication model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class MoleculePublication(BaseModel):
    """Association between molecule and publication."""
    model_config = ConfigDict(from_attributes=True)

    molecule_id: UUID
    publication_id: UUID
    relevance_score: Optional[float] = None
    mention_context: Optional[str] = None
    is_primary_subject: bool = False


class PublicationSummary(BaseModel):
    """Summary view of publication."""
    id: UUID
    doi: Optional[str]
    title: str
    publication_year: Optional[int]
    journal_name: Optional[str]
    first_author: Optional[str]
    cited_by_count: Optional[int]
