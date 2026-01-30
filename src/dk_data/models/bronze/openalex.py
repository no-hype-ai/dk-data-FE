"""
Bronze OpenAlex Models

Typed extraction from raw_openalex JSON.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class BronzeOpenAlexWorkBase(BaseModel):
    """Base fields for Bronze OpenAlex work (publication)."""
    openalex_id: str = Field(..., description="OpenAlex Work ID")
    doi: Optional[str] = None
    pmid: Optional[str] = None
    pmcid: Optional[str] = None
    
    # Title and abstract
    title: Optional[str] = None
    display_name: Optional[str] = None
    abstract: Optional[str] = None
    
    # Publication info
    publication_date: Optional[date] = None
    publication_year: Optional[int] = None
    type: Optional[str] = None
    is_retracted: Optional[bool] = None
    is_paratext: Optional[bool] = None
    
    # Venue
    host_venue: Optional[Dict[str, Any]] = None
    journal_name: Optional[str] = None
    journal_issn: Optional[List[str]] = None
    publisher: Optional[str] = None
    
    # Authors
    authorships: Optional[List[Dict[str, Any]]] = None
    author_names: Optional[List[str]] = None
    first_author: Optional[str] = None
    last_author: Optional[str] = None
    
    # Institutions
    institutions: Optional[List[Dict[str, Any]]] = None
    
    # Citations
    cited_by_count: Optional[int] = None
    is_oa: Optional[bool] = None
    oa_status: Optional[str] = None
    oa_url: Optional[str] = None
    
    # Concepts (topics)
    concepts: Optional[List[Dict[str, Any]]] = None
    
    # References
    referenced_works: Optional[List[str]] = None
    related_works: Optional[List[str]] = None
    
    # Mesh terms
    mesh: Optional[List[Dict[str, Any]]] = None


class BronzeOpenAlexWork(BronzeOpenAlexWorkBase):
    """Full Bronze OpenAlex work model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_id: UUID
    processed_at: datetime
    created_at: datetime
    updated_at: datetime
    extraction_version: str = "1.0"
