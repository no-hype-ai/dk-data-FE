"""
Alerts API Routes

Endpoints for managing pipeline and data quality alerts.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from enum import Enum
import logging
import json

from ..dependencies import get_db_pool, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])


# Enums

class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Alert types."""
    PIPELINE_FAILURE = "pipeline_failure"
    PIPELINE_DELAYED = "pipeline_delayed"
    DATA_QUALITY = "data_quality"
    SYNC_FAILURE = "sync_failure"
    CREDENTIAL_EXPIRING = "credential_expiring"
    RESOLUTION_QUEUE = "resolution_queue"
    QUARANTINE_THRESHOLD = "quarantine_threshold"
    SOURCE_UNAVAILABLE = "source_unavailable"
    RATE_LIMIT = "rate_limit"
    SCHEMA_CHANGE = "schema_change"


class AlertStatus(str, Enum):
    """Alert status."""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SILENCED = "silenced"


class NotificationChannel(str, Enum):
    """Notification channels."""
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    PAGERDUTY = "pagerduty"


# Request/Response Models

class CreateAlertRuleRequest(BaseModel):
    """Request to create an alert rule."""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    alert_type: AlertType
    severity: AlertSeverity = AlertSeverity.WARNING
    condition: dict = Field(..., description="Condition definition (metric, threshold, etc.)")
    notification_channels: List[NotificationChannel] = [NotificationChannel.EMAIL]
    cooldown_minutes: int = Field(default=15, ge=1, le=1440)
    enabled: bool = True


class UpdateAlertRuleRequest(BaseModel):
    """Request to update an alert rule."""
    name: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[AlertSeverity] = None
    condition: Optional[dict] = None
    notification_channels: Optional[List[NotificationChannel]] = None
    cooldown_minutes: Optional[int] = None
    enabled: Optional[bool] = None


class AlertRuleResponse(BaseModel):
    """Alert rule response."""
    id: str
    name: str
    description: Optional[str]
    alert_type: str
    severity: str
    condition: dict
    notification_channels: List[str]
    cooldown_minutes: int
    enabled: bool
    created_at: datetime
    updated_at: datetime
    last_triggered: Optional[datetime]
    trigger_count: int


class AlertResponse(BaseModel):
    """Alert instance response."""
    id: str
    rule_id: str
    rule_name: str
    alert_type: str
    severity: str
    status: str
    title: str
    message: str
    details: Optional[dict]
    created_at: datetime
    acknowledged_at: Optional[datetime]
    resolved_at: Optional[datetime]
    acknowledged_by: Optional[str]


class AlertListResponse(BaseModel):
    """List of alerts response."""
    alerts: List[AlertResponse]
    total: int
    active_count: int
    acknowledged_count: int


class AlertSummaryResponse(BaseModel):
    """Alert summary response."""
    total_active: int
    by_severity: dict
    by_type: dict
    recent_alerts: List[AlertResponse]


class AcknowledgeRequest(BaseModel):
    """Request to acknowledge alert(s)."""
    alert_ids: List[str]
    note: Optional[str] = None


class SilenceRequest(BaseModel):
    """Request to silence alerts."""
    alert_type: Optional[AlertType] = None
    rule_id: Optional[str] = None
    duration_minutes: int = Field(default=60, ge=1, le=10080)  # Max 1 week
    reason: str


# Alert Rule Endpoints

@router.post("/rules", response_model=AlertRuleResponse)
async def create_alert_rule(
    request: CreateAlertRuleRequest,
    user: dict = Depends(get_current_user),
):
    """
    Create a new alert rule.

    Alert rules define conditions that trigger alerts when met.
    """
    # Require admin or data_ops role
    if user.get("role") not in ("admin", "data_ops"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    db_pool = await get_db_pool()

    rule_id = uuid4()
    now = datetime.utcnow()

    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO platform.alert_rules (
                id, name, description, alert_type, severity,
                condition, notification_channels, cooldown_minutes,
                enabled, created_at, updated_at, created_by
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $10, $11)
        """,
            rule_id, request.name, request.description,
            request.alert_type.value, request.severity.value,
            json.dumps(request.condition),
            [c.value for c in request.notification_channels],
            request.cooldown_minutes, request.enabled, now, user["id"]
        )

    logger.info(f"Created alert rule {rule_id}: {request.name}")

    return AlertRuleResponse(
        id=str(rule_id),
        name=request.name,
        description=request.description,
        alert_type=request.alert_type.value,
        severity=request.severity.value,
        condition=request.condition,
        notification_channels=[c.value for c in request.notification_channels],
        cooldown_minutes=request.cooldown_minutes,
        enabled=request.enabled,
        created_at=now,
        updated_at=now,
        last_triggered=None,
        trigger_count=0,
    )


@router.get("/rules", response_model=List[AlertRuleResponse])
async def list_alert_rules(
    alert_type: Optional[AlertType] = None,
    enabled: Optional[bool] = None,
    user: dict = Depends(get_current_user),
):
    """List all alert rules."""
    db_pool = await get_db_pool()

    async with db_pool.acquire() as conn:
        query = "SELECT * FROM platform.alert_rules WHERE 1=1"
        params = []
        param_idx = 1

        if alert_type:
            query += f" AND alert_type = ${param_idx}"
            params.append(alert_type.value)
            param_idx += 1

        if enabled is not None:
            query += f" AND enabled = ${param_idx}"
            params.append(enabled)
            param_idx += 1

        query += " ORDER BY created_at DESC"

        rows = await conn.fetch(query, *params)

    return [
        AlertRuleResponse(
            id=str(r['id']),
            name=r['name'],
            description=r['description'],
            alert_type=r['alert_type'],
            severity=r['severity'],
            condition=json.loads(r['condition']) if isinstance(r['condition'], str) else r['condition'],
            notification_channels=r['notification_channels'],
            cooldown_minutes=r['cooldown_minutes'],
            enabled=r['enabled'],
            created_at=r['created_at'],
            updated_at=r['updated_at'],
            last_triggered=r.get('last_triggered'),
            trigger_count=r.get('trigger_count', 0),
        )
        for r in rows
    ]


@router.get("/rules/{rule_id}", response_model=AlertRuleResponse)
async def get_alert_rule(
    rule_id: UUID,
    user: dict = Depends(get_current_user),
):
    """Get an alert rule by ID."""
    db_pool = await get_db_pool()

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM platform.alert_rules WHERE id = $1",
            rule_id
        )

    if not row:
        raise HTTPException(status_code=404, detail="Alert rule not found")

    return AlertRuleResponse(
        id=str(row['id']),
        name=row['name'],
        description=row['description'],
        alert_type=row['alert_type'],
        severity=row['severity'],
        condition=json.loads(row['condition']) if isinstance(row['condition'], str) else row['condition'],
        notification_channels=row['notification_channels'],
        cooldown_minutes=row['cooldown_minutes'],
        enabled=row['enabled'],
        created_at=row['created_at'],
        updated_at=row['updated_at'],
        last_triggered=row.get('last_triggered'),
        trigger_count=row.get('trigger_count', 0),
    )


@router.patch("/rules/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    rule_id: UUID,
    request: UpdateAlertRuleRequest,
    user: dict = Depends(get_current_user),
):
    """Update an alert rule."""
    if user.get("role") not in ("admin", "data_ops"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    db_pool = await get_db_pool()

    async with db_pool.acquire() as conn:
        # Check if rule exists
        existing = await conn.fetchrow(
            "SELECT * FROM platform.alert_rules WHERE id = $1",
            rule_id
        )

        if not existing:
            raise HTTPException(status_code=404, detail="Alert rule not found")

        # Build update query
        updates = ["updated_at = NOW()"]
        params = []
        param_idx = 1

        if request.name is not None:
            updates.append(f"name = ${param_idx}")
            params.append(request.name)
            param_idx += 1

        if request.description is not None:
            updates.append(f"description = ${param_idx}")
            params.append(request.description)
            param_idx += 1

        if request.severity is not None:
            updates.append(f"severity = ${param_idx}")
            params.append(request.severity.value)
            param_idx += 1

        if request.condition is not None:
            updates.append(f"condition = ${param_idx}")
            params.append(json.dumps(request.condition))
            param_idx += 1

        if request.notification_channels is not None:
            updates.append(f"notification_channels = ${param_idx}")
            params.append([c.value for c in request.notification_channels])
            param_idx += 1

        if request.cooldown_minutes is not None:
            updates.append(f"cooldown_minutes = ${param_idx}")
            params.append(request.cooldown_minutes)
            param_idx += 1

        if request.enabled is not None:
            updates.append(f"enabled = ${param_idx}")
            params.append(request.enabled)
            param_idx += 1

        params.append(rule_id)

        await conn.execute(
            f"UPDATE platform.alert_rules SET {', '.join(updates)} WHERE id = ${param_idx}",
            *params
        )

        # Fetch updated rule
        row = await conn.fetchrow(
            "SELECT * FROM platform.alert_rules WHERE id = $1",
            rule_id
        )

    return AlertRuleResponse(
        id=str(row['id']),
        name=row['name'],
        description=row['description'],
        alert_type=row['alert_type'],
        severity=row['severity'],
        condition=json.loads(row['condition']) if isinstance(row['condition'], str) else row['condition'],
        notification_channels=row['notification_channels'],
        cooldown_minutes=row['cooldown_minutes'],
        enabled=row['enabled'],
        created_at=row['created_at'],
        updated_at=row['updated_at'],
        last_triggered=row.get('last_triggered'),
        trigger_count=row.get('trigger_count', 0),
    )


@router.delete("/rules/{rule_id}")
async def delete_alert_rule(
    rule_id: UUID,
    user: dict = Depends(get_current_user),
):
    """Delete an alert rule."""
    if user.get("role") not in ("admin", "data_ops"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    db_pool = await get_db_pool()

    async with db_pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM platform.alert_rules WHERE id = $1",
            rule_id
        )

    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Alert rule not found")

    return {"message": "Alert rule deleted successfully"}


# Alert Instance Endpoints

@router.get("", response_model=AlertListResponse)
async def list_alerts(
    status: Optional[AlertStatus] = None,
    severity: Optional[AlertSeverity] = None,
    alert_type: Optional[AlertType] = None,
    since: Optional[datetime] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    """
    List alerts with optional filtering.

    Returns alerts sorted by creation time (newest first).
    """
    db_pool = await get_db_pool()

    async with db_pool.acquire() as conn:
        # Build query
        query = """
            SELECT a.*, r.name as rule_name
            FROM platform.alerts a
            JOIN platform.alert_rules r ON r.id = a.rule_id
            WHERE 1=1
        """
        count_query = "SELECT COUNT(*) FROM platform.alerts a WHERE 1=1"
        params = []
        param_idx = 1

        if status:
            query += f" AND a.status = ${param_idx}"
            count_query += f" AND a.status = ${param_idx}"
            params.append(status.value)
            param_idx += 1

        if severity:
            query += f" AND a.severity = ${param_idx}"
            count_query += f" AND a.severity = ${param_idx}"
            params.append(severity.value)
            param_idx += 1

        if alert_type:
            query += f" AND a.alert_type = ${param_idx}"
            count_query += f" AND a.alert_type = ${param_idx}"
            params.append(alert_type.value)
            param_idx += 1

        if since:
            query += f" AND a.created_at >= ${param_idx}"
            count_query += f" AND a.created_at >= ${param_idx}"
            params.append(since)
            param_idx += 1

        # Get counts
        total = await conn.fetchval(count_query, *params)
        active_count = await conn.fetchval(
            "SELECT COUNT(*) FROM platform.alerts WHERE status = 'active'"
        )
        ack_count = await conn.fetchval(
            "SELECT COUNT(*) FROM platform.alerts WHERE status = 'acknowledged'"
        )

        query += f" ORDER BY a.created_at DESC LIMIT ${param_idx} OFFSET ${param_idx + 1}"
        params.extend([limit, offset])

        rows = await conn.fetch(query, *params)

    alerts = [
        AlertResponse(
            id=str(r['id']),
            rule_id=str(r['rule_id']),
            rule_name=r['rule_name'],
            alert_type=r['alert_type'],
            severity=r['severity'],
            status=r['status'],
            title=r['title'],
            message=r['message'],
            details=json.loads(r['details']) if r['details'] and isinstance(r['details'], str) else r['details'],
            created_at=r['created_at'],
            acknowledged_at=r.get('acknowledged_at'),
            resolved_at=r.get('resolved_at'),
            acknowledged_by=r.get('acknowledged_by'),
        )
        for r in rows
    ]

    return AlertListResponse(
        alerts=alerts,
        total=total or 0,
        active_count=active_count or 0,
        acknowledged_count=ack_count or 0,
    )


@router.get("/summary", response_model=AlertSummaryResponse)
async def get_alert_summary(
    user: dict = Depends(get_current_user),
):
    """Get a summary of current alerts."""
    db_pool = await get_db_pool()

    async with db_pool.acquire() as conn:
        # Active count
        total_active = await conn.fetchval(
            "SELECT COUNT(*) FROM platform.alerts WHERE status = 'active'"
        ) or 0

        # By severity
        severity_rows = await conn.fetch("""
            SELECT severity, COUNT(*) as count
            FROM platform.alerts
            WHERE status = 'active'
            GROUP BY severity
        """)
        by_severity = {r['severity']: r['count'] for r in severity_rows}

        # By type
        type_rows = await conn.fetch("""
            SELECT alert_type, COUNT(*) as count
            FROM platform.alerts
            WHERE status = 'active'
            GROUP BY alert_type
        """)
        by_type = {r['alert_type']: r['count'] for r in type_rows}

        # Recent alerts
        recent = await conn.fetch("""
            SELECT a.*, r.name as rule_name
            FROM platform.alerts a
            JOIN platform.alert_rules r ON r.id = a.rule_id
            WHERE a.status IN ('active', 'acknowledged')
            ORDER BY a.created_at DESC
            LIMIT 10
        """)

    recent_alerts = [
        AlertResponse(
            id=str(r['id']),
            rule_id=str(r['rule_id']),
            rule_name=r['rule_name'],
            alert_type=r['alert_type'],
            severity=r['severity'],
            status=r['status'],
            title=r['title'],
            message=r['message'],
            details=json.loads(r['details']) if r['details'] and isinstance(r['details'], str) else r['details'],
            created_at=r['created_at'],
            acknowledged_at=r.get('acknowledged_at'),
            resolved_at=r.get('resolved_at'),
            acknowledged_by=r.get('acknowledged_by'),
        )
        for r in recent
    ]

    return AlertSummaryResponse(
        total_active=total_active,
        by_severity=by_severity,
        by_type=by_type,
        recent_alerts=recent_alerts,
    )


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: UUID,
    user: dict = Depends(get_current_user),
):
    """Get an alert by ID."""
    db_pool = await get_db_pool()

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT a.*, r.name as rule_name
            FROM platform.alerts a
            JOIN platform.alert_rules r ON r.id = a.rule_id
            WHERE a.id = $1
        """, alert_id)

    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")

    return AlertResponse(
        id=str(row['id']),
        rule_id=str(row['rule_id']),
        rule_name=row['rule_name'],
        alert_type=row['alert_type'],
        severity=row['severity'],
        status=row['status'],
        title=row['title'],
        message=row['message'],
        details=json.loads(row['details']) if row['details'] and isinstance(row['details'], str) else row['details'],
        created_at=row['created_at'],
        acknowledged_at=row.get('acknowledged_at'),
        resolved_at=row.get('resolved_at'),
        acknowledged_by=row.get('acknowledged_by'),
    )


@router.post("/acknowledge")
async def acknowledge_alerts(
    request: AcknowledgeRequest,
    user: dict = Depends(get_current_user),
):
    """Acknowledge one or more alerts."""
    db_pool = await get_db_pool()

    acknowledged = 0
    async with db_pool.acquire() as conn:
        for alert_id_str in request.alert_ids:
            try:
                alert_id = UUID(alert_id_str)
                result = await conn.execute("""
                    UPDATE platform.alerts
                    SET status = 'acknowledged',
                        acknowledged_at = NOW(),
                        acknowledged_by = $2,
                        ack_note = $3
                    WHERE id = $1 AND status = 'active'
                """, alert_id, user["id"], request.note)

                if result == "UPDATE 1":
                    acknowledged += 1
            except ValueError:
                continue

    return {
        "message": f"Acknowledged {acknowledged} alert(s)",
        "acknowledged_count": acknowledged
    }


@router.post("/{alert_id}/resolve")
async def resolve_alert(
    alert_id: UUID,
    note: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Resolve an alert."""
    db_pool = await get_db_pool()

    async with db_pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE platform.alerts
            SET status = 'resolved',
                resolved_at = NOW(),
                resolution_note = $2
            WHERE id = $1 AND status IN ('active', 'acknowledged')
        """, alert_id, note)

    if result == "UPDATE 0":
        raise HTTPException(
            status_code=400,
            detail="Alert not found or already resolved"
        )

    return {"message": "Alert resolved successfully"}


@router.post("/silence")
async def silence_alerts(
    request: SilenceRequest,
    user: dict = Depends(get_current_user),
):
    """
    Silence alerts for a specified duration.

    Can silence by alert type, specific rule, or both.
    """
    if user.get("role") not in ("admin", "data_ops"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    db_pool = await get_db_pool()

    silence_id = uuid4()
    expires_at = datetime.utcnow() + timedelta(minutes=request.duration_minutes)

    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO platform.alert_silences (
                id, alert_type, rule_id, reason, expires_at, created_by, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, NOW())
        """,
            silence_id,
            request.alert_type.value if request.alert_type else None,
            UUID(request.rule_id) if request.rule_id else None,
            request.reason,
            expires_at,
            user["id"]
        )

    logger.info(f"Created alert silence {silence_id} until {expires_at}")

    return {
        "silence_id": str(silence_id),
        "expires_at": expires_at.isoformat(),
        "message": f"Alerts silenced for {request.duration_minutes} minutes"
    }


@router.get("/silences/active")
async def list_active_silences(
    user: dict = Depends(get_current_user),
):
    """List all active alert silences."""
    db_pool = await get_db_pool()

    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM platform.alert_silences
            WHERE expires_at > NOW()
            ORDER BY expires_at
        """)

    return {
        "silences": [
            {
                "id": str(r['id']),
                "alert_type": r['alert_type'],
                "rule_id": str(r['rule_id']) if r['rule_id'] else None,
                "reason": r['reason'],
                "expires_at": r['expires_at'].isoformat(),
                "created_by": r['created_by'],
                "created_at": r['created_at'].isoformat(),
            }
            for r in rows
        ]
    }


@router.delete("/silences/{silence_id}")
async def delete_silence(
    silence_id: UUID,
    user: dict = Depends(get_current_user),
):
    """Delete an alert silence."""
    if user.get("role") not in ("admin", "data_ops"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    db_pool = await get_db_pool()

    async with db_pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM platform.alert_silences WHERE id = $1",
            silence_id
        )

    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Silence not found")

    return {"message": "Silence deleted successfully"}
