"""
Alert Configuration Models

Pydantic models for user alert configurations.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime, time
from typing import Optional, List, Dict, Any
from uuid import UUID
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class AlertEventType(str, Enum):
    """Types of events that can trigger alerts."""
    # Lifecycle events
    STAGE_TRANSITION = "stage_transition"
    STAGE_VALIDATION = "stage_validation"
    LIFECYCLE_REGRESSION = "lifecycle_regression"

    # Trial events
    NEW_TRIAL = "new_trial"
    TRIAL_STATUS_CHANGE = "trial_status_change"
    TRIAL_RESULTS_POSTED = "trial_results_posted"
    TRIAL_TERMINATED = "trial_terminated"

    # Safety events
    NEW_SAFETY_SIGNAL = "new_safety_signal"
    BOXED_WARNING_ADDED = "boxed_warning_added"
    SAFETY_ALERT = "safety_alert"

    # Regulatory events
    FDA_APPROVAL = "fda_approval"
    EMA_APPROVAL = "ema_approval"
    REGULATORY_ACTION = "regulatory_action"
    LABEL_UPDATE = "label_update"

    # Publication events
    NEW_PUBLICATION = "new_publication"
    PUBLICATION_MILESTONE = "publication_milestone"

    # Patent events
    PATENT_EXPIRY_APPROACHING = "patent_expiry_approaching"
    NEW_PATENT_FILED = "new_patent_filed"
    PATENT_LITIGATION = "patent_litigation"

    # Competitive events
    COMPETITOR_APPROVAL = "competitor_approval"
    COMPETITOR_TRIAL_START = "competitor_trial_start"
    MARKET_SHARE_CHANGE = "market_share_change"

    # Data quality events
    DATA_QUALITY_ISSUE = "data_quality_issue"
    SOURCE_SYNC_FAILURE = "source_sync_failure"


class DeliveryChannel(str, Enum):
    """Alert delivery channels."""
    EMAIL = "email"
    IN_APP = "in_app"
    WEBHOOK = "webhook"
    SLACK = "slack"
    SMS = "sms"


class DigestFrequency(str, Enum):
    """Frequency for digest delivery."""
    IMMEDIATE = "immediate"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class AlertPriority(str, Enum):
    """Alert priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertConfigStatus(str, Enum):
    """Status of alert configuration."""
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


class AlertDeliverySettings(BaseModel):
    """Settings for alert delivery."""
    channels: List[DeliveryChannel] = Field(default=[DeliveryChannel.IN_APP, DeliveryChannel.EMAIL])
    digest_frequency: DigestFrequency = DigestFrequency.IMMEDIATE
    digest_time: Optional[time] = None  # Preferred time for digest delivery
    quiet_hours_start: Optional[time] = None
    quiet_hours_end: Optional[time] = None
    webhook_url: Optional[str] = None
    slack_channel: Optional[str] = None


class AlertCondition(BaseModel):
    """Condition for alert triggering."""
    field: str
    operator: str  # eq, ne, gt, lt, gte, lte, contains, starts_with
    value: Any
    and_conditions: Optional[List['AlertCondition']] = None
    or_conditions: Optional[List['AlertCondition']] = None


class AlertConfigBase(BaseModel):
    """Base alert configuration fields."""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    event_types: List[AlertEventType] = Field(..., min_length=1)
    priority: AlertPriority = AlertPriority.MEDIUM
    delivery_settings: AlertDeliverySettings = Field(default_factory=AlertDeliverySettings)


class AlertConfigCreate(AlertConfigBase):
    """Model for creating an alert configuration."""
    molecule_ids: Optional[List[UUID]] = None  # Specific molecules to monitor
    therapeutic_areas: Optional[List[str]] = None  # All molecules in these areas
    lifecycle_stages: Optional[List[str]] = None  # All molecules in these stages
    conditions: Optional[List[AlertCondition]] = None  # Additional filter conditions
    global_scope: bool = False  # Apply to all tracked molecules


class AlertConfigUpdate(BaseModel):
    """Model for updating an alert configuration."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    event_types: Optional[List[AlertEventType]] = None
    priority: Optional[AlertPriority] = None
    delivery_settings: Optional[AlertDeliverySettings] = None
    molecule_ids: Optional[List[UUID]] = None
    therapeutic_areas: Optional[List[str]] = None
    lifecycle_stages: Optional[List[str]] = None
    conditions: Optional[List[AlertCondition]] = None
    status: Optional[AlertConfigStatus] = None


class AlertConfig(AlertConfigBase):
    """Full alert configuration model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    molecule_ids: Optional[List[UUID]] = None
    therapeutic_areas: Optional[List[str]] = None
    lifecycle_stages: Optional[List[str]] = None
    conditions: Optional[List[AlertCondition]] = None
    global_scope: bool = False
    status: AlertConfigStatus = AlertConfigStatus.ACTIVE
    created_at: datetime
    updated_at: datetime
    last_triggered_at: Optional[datetime] = None
    trigger_count: int = 0


class AlertHistoryBase(BaseModel):
    """Base alert history fields."""
    alert_config_id: UUID
    event_type: AlertEventType
    priority: AlertPriority
    title: str
    message: str
    details: Optional[Dict[str, Any]] = None


class AlertHistoryCreate(AlertHistoryBase):
    """Model for creating an alert history entry."""
    molecule_id: Optional[UUID] = None
    entity_type: Optional[str] = None
    entity_id: Optional[UUID] = None


class AlertHistory(AlertHistoryBase):
    """Full alert history model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    molecule_id: Optional[UUID] = None
    entity_type: Optional[str] = None
    entity_id: Optional[UUID] = None
    is_read: bool = False
    is_dismissed: bool = False
    delivered_via: Optional[List[str]] = None
    created_at: datetime
    read_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None


class AlertHistoryWithMolecule(AlertHistory):
    """Alert history with molecule details."""
    molecule_name: Optional[str] = None
    molecule_inchi_key: Optional[str] = None
    molecule_development_status: Optional[str] = None


class AlertHistoryQuery(BaseModel):
    """Query parameters for alert history."""
    user_id: Optional[UUID] = None
    alert_config_id: Optional[UUID] = None
    molecule_id: Optional[UUID] = None
    event_types: Optional[List[AlertEventType]] = None
    priority: Optional[AlertPriority] = None
    is_read: Optional[bool] = None
    is_dismissed: Optional[bool] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class AlertHistoryResponse(BaseModel):
    """Paginated alert history response."""
    alerts: List[AlertHistoryWithMolecule]
    total: int
    unread_count: int
    limit: int
    offset: int
    has_more: bool


class AlertSummary(BaseModel):
    """Summary of user's alerts."""
    total_alerts: int = 0
    unread_count: int = 0
    by_priority: Dict[str, int] = Field(default_factory=dict)
    by_event_type: Dict[str, int] = Field(default_factory=dict)
    recent_alerts: List[AlertHistoryWithMolecule] = Field(default_factory=list)
    active_configs: int = 0
    paused_configs: int = 0


class AlertDigest(BaseModel):
    """Alert digest for batch delivery."""
    user_id: UUID
    frequency: DigestFrequency
    period_start: datetime
    period_end: datetime
    total_alerts: int
    by_molecule: Dict[str, List[AlertHistoryWithMolecule]]
    by_priority: Dict[str, List[AlertHistoryWithMolecule]]
    summary: str


# Self-reference for nested conditions
AlertCondition.model_rebuild()
