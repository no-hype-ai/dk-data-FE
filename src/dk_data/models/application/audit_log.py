"""
Audit Log Models

Pydantic models for onboarding and platform audit logging.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class AuditAction(str, Enum):
    """Types of auditable actions."""
    # Molecule actions
    MOLECULE_ONBOARDED = "molecule_onboarded"
    MOLECULE_UPDATED = "molecule_updated"
    MOLECULE_ARCHIVED = "molecule_archived"
    MOLECULE_RESTORED = "molecule_restored"

    # Lifecycle actions
    LIFECYCLE_STAGE_CHANGED = "lifecycle_stage_changed"
    LIFECYCLE_VALIDATED = "lifecycle_validated"
    LIFECYCLE_OVERRIDE = "lifecycle_override"

    # Evidence actions
    EVIDENCE_ADDED = "evidence_added"
    EVIDENCE_REMOVED = "evidence_removed"
    EVIDENCE_VERIFIED = "evidence_verified"

    # Resolution actions
    RESOLUTION_COMPLETED = "resolution_completed"
    RESOLUTION_REJECTED = "resolution_rejected"
    RESOLUTION_MERGED = "resolution_merged"
    QUARANTINE_ADDED = "quarantine_added"
    QUARANTINE_RESOLVED = "quarantine_resolved"

    # Tracking actions
    TRACKING_STARTED = "tracking_started"
    TRACKING_STOPPED = "tracking_stopped"
    ALERT_CONFIGURED = "alert_configured"
    ALERT_TRIGGERED = "alert_triggered"

    # Data source actions
    SOURCE_REGISTERED = "source_registered"
    SOURCE_SYNCED = "source_synced"
    SOURCE_DISABLED = "source_disabled"
    CREDENTIALS_UPDATED = "credentials_updated"

    # Admin actions
    USER_ROLE_CHANGED = "user_role_changed"
    SYSTEM_CONFIG_CHANGED = "system_config_changed"
    BULK_OPERATION = "bulk_operation"


class AuditCategory(str, Enum):
    """Categories for audit events."""
    MOLECULE = "molecule"
    LIFECYCLE = "lifecycle"
    EVIDENCE = "evidence"
    RESOLUTION = "resolution"
    TRACKING = "tracking"
    DATA_SOURCE = "data_source"
    ADMIN = "admin"
    SYSTEM = "system"


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditLogBase(BaseModel):
    """Base audit log fields."""
    action: AuditAction
    category: AuditCategory
    severity: AuditSeverity = AuditSeverity.INFO
    description: str
    details: Optional[Dict[str, Any]] = None


class AuditLogCreate(AuditLogBase):
    """Model for creating an audit log entry."""
    user_id: Optional[UUID] = None
    entity_type: Optional[str] = None  # e.g., "molecule", "user", "data_source"
    entity_id: Optional[UUID] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class AuditLog(AuditLogBase):
    """Full audit log model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: Optional[UUID] = None
    entity_type: Optional[str] = None
    entity_id: Optional[UUID] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime


class AuditLogWithUser(AuditLog):
    """Audit log with user details."""
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    user_role: Optional[str] = None


class AuditLogQuery(BaseModel):
    """Query parameters for audit log search."""
    user_id: Optional[UUID] = None
    entity_type: Optional[str] = None
    entity_id: Optional[UUID] = None
    action: Optional[AuditAction] = None
    category: Optional[AuditCategory] = None
    severity: Optional[AuditSeverity] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    search_text: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class AuditLogResponse(BaseModel):
    """Paginated audit log response."""
    logs: List[AuditLogWithUser]
    total: int
    limit: int
    offset: int
    has_more: bool


class AuditStats(BaseModel):
    """Statistics for audit logs."""
    total_events: int = 0
    by_category: Dict[str, int] = Field(default_factory=dict)
    by_action: Dict[str, int] = Field(default_factory=dict)
    by_severity: Dict[str, int] = Field(default_factory=dict)
    by_user: Dict[str, int] = Field(default_factory=dict)
    recent_errors: List[AuditLog] = Field(default_factory=list)


class OnboardingAuditEntry(BaseModel):
    """Specialized audit entry for molecule onboarding."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    molecule_id: UUID
    molecule_name: str
    user_id: UUID
    step_number: int
    step_name: str
    action: str  # 'started', 'completed', 'skipped', 'failed'
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime


class OnboardingAuditSummary(BaseModel):
    """Summary of onboarding audit for a molecule."""
    molecule_id: UUID
    molecule_name: str
    total_steps: int
    completed_steps: int
    skipped_steps: int
    failed_steps: int
    total_duration_seconds: float
    onboarded_by: str
    onboarded_at: datetime
    last_updated_at: datetime
    steps: List[OnboardingAuditEntry]
