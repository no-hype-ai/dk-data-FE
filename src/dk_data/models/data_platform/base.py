"""
Data Platform Base Models

Shared Pydantic base models for all data platform layers.

Part of DK Data Platform Medallion Architecture
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class TimestampMixin(BaseModel):
    """Mixin for timestamp fields."""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class BaseDBModel(BaseModel):
    """Base model for database entities."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class RawBaseModel(BaseDBModel, TimestampMixin):
    """Base model for Raw layer tables."""
    request_id: str
    request_timestamp: datetime = Field(default_factory=datetime.utcnow)
    api_endpoint: str
    request_params: Optional[Dict[str, Any]] = None
    response_status: int
    response_headers: Optional[Dict[str, str]] = None
    response_body: Dict[str, Any]
    response_body_hash: str
    processed_to_bronze: bool = False
    processed_at: Optional[datetime] = None


class BronzeBaseModel(BaseDBModel, TimestampMixin):
    """Base model for Bronze layer tables."""
    raw_source_id: UUID
    source: str
    source_updated_at: Optional[datetime] = None
    raw_json: Dict[str, Any]
    processed_to_silver: bool = False


class SilverBaseModel(BaseDBModel, TimestampMixin):
    """Base model for Silver layer tables."""
    source: str
    source_updated_at: Optional[datetime] = None


class GoldBaseModel(BaseDBModel):
    """Base model for Gold layer views."""
    model_config = ConfigDict(from_attributes=True)


class PaginatedResponse(BaseModel):
    """Generic paginated response."""
    items: List[Any]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def create(cls, items: List[Any], total: int, page: int, page_size: int):
        pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(items=items, total=total, page=page, page_size=page_size, pages=pages)


class APIResponse(BaseModel):
    """Standard API response wrapper."""
    success: bool = True
    data: Optional[Any] = None
    message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ErrorResponse(BaseModel):
    """Error response model."""
    success: bool = False
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
