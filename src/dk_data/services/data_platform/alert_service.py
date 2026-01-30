"""
Alert Service

Handles molecule change detection and user notification delivery.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4
from enum import Enum
from dataclasses import dataclass
import logging
import asyncio

logger = logging.getLogger(__name__)


class AlertType(str, Enum):
    """Types of alerts."""
    TRIAL_NEW = "trial_new"
    TRIAL_STATUS_CHANGE = "trial_status_change"
    TRIAL_RESULTS = "trial_results"
    SAFETY_SIGNAL = "safety_signal"
    LABEL_UPDATE = "label_update"
    LABEL_BOXED_WARNING = "label_boxed_warning"
    REGULATORY_APPROVAL = "regulatory_approval"
    REGULATORY_REJECTION = "regulatory_rejection"
    PUBLICATION_NEW = "publication_new"
    PATENT_EVENT = "patent_event"
    STAGE_CHANGE = "stage_change"
    DATA_REFRESH = "data_refresh"


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DeliveryMethod(str, Enum):
    """Alert delivery methods."""
    IN_APP = "in_app"
    EMAIL = "email"
    WEBHOOK = "webhook"


class DeliveryFrequency(str, Enum):
    """Alert delivery frequency."""
    IMMEDIATE = "immediate"
    DAILY_DIGEST = "daily_digest"
    WEEKLY_DIGEST = "weekly_digest"


@dataclass
class Alert:
    """Alert data structure."""
    id: UUID
    user_id: UUID
    molecule_id: UUID
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    description: Optional[str]
    data: Optional[Dict[str, Any]]
    source_type: Optional[str]
    source_id: Optional[str]
    source_url: Optional[str]
    created_at: datetime
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None


class AlertService:
    """
    Service for managing molecule alerts and notifications.

    Features:
    - Change detection for tracked molecules
    - Alert generation and severity classification
    - Multi-channel delivery (in-app, email, webhook)
    - Digest batching (daily/weekly)
    """

    # Severity mapping by alert type
    DEFAULT_SEVERITY = {
        AlertType.TRIAL_NEW: AlertSeverity.MEDIUM,
        AlertType.TRIAL_STATUS_CHANGE: AlertSeverity.LOW,
        AlertType.TRIAL_RESULTS: AlertSeverity.HIGH,
        AlertType.SAFETY_SIGNAL: AlertSeverity.HIGH,
        AlertType.LABEL_UPDATE: AlertSeverity.MEDIUM,
        AlertType.LABEL_BOXED_WARNING: AlertSeverity.CRITICAL,
        AlertType.REGULATORY_APPROVAL: AlertSeverity.HIGH,
        AlertType.REGULATORY_REJECTION: AlertSeverity.HIGH,
        AlertType.PUBLICATION_NEW: AlertSeverity.LOW,
        AlertType.PATENT_EVENT: AlertSeverity.MEDIUM,
        AlertType.STAGE_CHANGE: AlertSeverity.HIGH,
        AlertType.DATA_REFRESH: AlertSeverity.INFO,
    }

    def __init__(self, db_pool, email_service=None, webhook_service=None):
        """
        Initialize alert service.

        Args:
            db_pool: Database connection pool
            email_service: Optional email delivery service
            webhook_service: Optional webhook delivery service
        """
        self.db_pool = db_pool
        self.email_service = email_service
        self.webhook_service = webhook_service

    async def create_molecule_update(
        self,
        molecule_id: UUID,
        alert_type: AlertType,
        title: str,
        description: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        source_url: Optional[str] = None,
        severity: Optional[AlertSeverity] = None,
    ) -> UUID:
        """
        Create a molecule update event.

        This records the change and triggers alerts for users tracking the molecule.
        """
        update_id = uuid4()
        final_severity = severity or self.DEFAULT_SEVERITY.get(alert_type, AlertSeverity.INFO)

        async with self.db_pool.acquire() as conn:
            # Record the update
            await conn.execute("""
                INSERT INTO application.molecule_updates
                (id, molecule_id, update_type, title, description, data,
                 source_type, source_id, source_url, severity)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """, update_id, molecule_id, alert_type.value, title, description,
            data, source_type, source_id, source_url, final_severity.value)

            # Find users tracking this molecule
            tracking_users = await conn.fetch("""
                SELECT DISTINCT utm.user_id, uac.alert_config_id,
                       uac.delivery_method, uac.delivery_frequency,
                       uac.webhook_url, uac.email_address
                FROM user_tracked_molecules utm
                LEFT JOIN user_alert_configs uac
                    ON utm.user_id = uac.user_id AND utm.molecule_id = uac.molecule_id
                WHERE utm.molecule_id = $1
                  AND (uac.is_active = TRUE OR uac.alert_config_id IS NULL)
            """, molecule_id)

            # Create alerts for each user
            for user in tracking_users:
                await self._create_user_alert(
                    conn=conn,
                    user_id=user['user_id'],
                    molecule_id=molecule_id,
                    update_id=update_id,
                    alert_type=alert_type,
                    severity=final_severity,
                    title=title,
                    description=description,
                    data=data,
                    alert_config=user,
                )

        return update_id

    async def _create_user_alert(
        self,
        conn,
        user_id: UUID,
        molecule_id: UUID,
        update_id: UUID,
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        description: Optional[str],
        data: Optional[Dict[str, Any]],
        alert_config: Dict[str, Any],
    ):
        """Create alert for a specific user."""
        alert_id = uuid4()
        delivery_method = alert_config.get('delivery_method') or 'in_app'
        delivery_frequency = alert_config.get('delivery_frequency') or 'immediate'

        # Check if alert type is enabled for this user
        if not await self._is_alert_enabled(conn, alert_config.get('alert_config_id'), alert_type):
            return

        await conn.execute("""
            INSERT INTO alert_history
            (alert_id, user_id, molecule_id, alert_config_id,
             alert_type, title, description, data, severity,
             delivery_method, delivery_status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """, alert_id, user_id, molecule_id, alert_config.get('alert_config_id'),
        alert_type.value, title, description, data, severity.value,
        delivery_method, 'pending')

        # Deliver immediately if configured
        if delivery_frequency == 'immediate':
            await self._deliver_alert(alert_id, delivery_method, alert_config)

    async def _is_alert_enabled(
        self,
        conn,
        alert_config_id: Optional[UUID],
        alert_type: AlertType
    ) -> bool:
        """Check if alert type is enabled for user."""
        if not alert_config_id:
            return True  # Default: all alerts enabled

        config = await conn.fetchrow("""
            SELECT alert_on_stage_change, alert_on_trial_update,
                   alert_on_safety_signal, alert_on_regulatory_action,
                   alert_on_patent_event, alert_on_publication
            FROM user_alert_configs
            WHERE alert_config_id = $1
        """, alert_config_id)

        if not config:
            return True

        type_mapping = {
            AlertType.STAGE_CHANGE: 'alert_on_stage_change',
            AlertType.TRIAL_NEW: 'alert_on_trial_update',
            AlertType.TRIAL_STATUS_CHANGE: 'alert_on_trial_update',
            AlertType.TRIAL_RESULTS: 'alert_on_trial_update',
            AlertType.SAFETY_SIGNAL: 'alert_on_safety_signal',
            AlertType.LABEL_UPDATE: 'alert_on_regulatory_action',
            AlertType.LABEL_BOXED_WARNING: 'alert_on_safety_signal',
            AlertType.REGULATORY_APPROVAL: 'alert_on_regulatory_action',
            AlertType.REGULATORY_REJECTION: 'alert_on_regulatory_action',
            AlertType.PUBLICATION_NEW: 'alert_on_publication',
            AlertType.PATENT_EVENT: 'alert_on_patent_event',
        }

        config_key = type_mapping.get(alert_type)
        return config.get(config_key, True) if config_key else True

    async def _deliver_alert(
        self,
        alert_id: UUID,
        delivery_method: str,
        alert_config: Dict[str, Any]
    ):
        """Deliver alert via configured method."""
        try:
            if delivery_method == 'email' and self.email_service:
                await self.email_service.send_alert(
                    alert_id=alert_id,
                    email=alert_config.get('email_address')
                )
            elif delivery_method == 'webhook' and self.webhook_service:
                await self.webhook_service.send_alert(
                    alert_id=alert_id,
                    webhook_url=alert_config.get('webhook_url')
                )

            # Mark as delivered
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    UPDATE alert_history
                    SET delivered_at = NOW(), delivery_status = 'delivered'
                    WHERE alert_id = $1
                """, alert_id)

        except Exception as e:
            logger.error(f"Failed to deliver alert {alert_id}: {e}")
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    UPDATE alert_history
                    SET delivery_status = 'failed', delivery_error = $2
                    WHERE alert_id = $1
                """, alert_id, str(e))

    async def get_user_alerts(
        self,
        user_id: UUID,
        unread_only: bool = False,
        molecule_id: Optional[UUID] = None,
        alert_type: Optional[AlertType] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get alerts for a user."""
        async with self.db_pool.acquire() as conn:
            query = """
                SELECT ah.*, sm.canonical_name as molecule_name
                FROM alert_history ah
                JOIN silver.molecules sm ON ah.molecule_id = sm.id
                WHERE ah.user_id = $1
            """
            params = [user_id]
            param_idx = 2

            if unread_only:
                query += f" AND ah.read_at IS NULL"

            if molecule_id:
                query += f" AND ah.molecule_id = ${param_idx}"
                params.append(molecule_id)
                param_idx += 1

            if alert_type:
                query += f" AND ah.alert_type = ${param_idx}"
                params.append(alert_type.value)
                param_idx += 1

            query += f" ORDER BY ah.created_at DESC LIMIT ${param_idx} OFFSET ${param_idx + 1}"
            params.extend([limit, offset])

            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    async def mark_alerts_read(
        self,
        user_id: UUID,
        alert_ids: Optional[List[UUID]] = None,
        molecule_id: Optional[UUID] = None,
        mark_all: bool = False,
    ) -> int:
        """Mark alerts as read."""
        async with self.db_pool.acquire() as conn:
            if mark_all:
                result = await conn.execute("""
                    UPDATE alert_history
                    SET read_at = NOW()
                    WHERE user_id = $1 AND read_at IS NULL
                """, user_id)
            elif molecule_id:
                result = await conn.execute("""
                    UPDATE alert_history
                    SET read_at = NOW()
                    WHERE user_id = $1 AND molecule_id = $2 AND read_at IS NULL
                """, user_id, molecule_id)
            elif alert_ids:
                result = await conn.execute("""
                    UPDATE alert_history
                    SET read_at = NOW()
                    WHERE user_id = $1 AND alert_id = ANY($2) AND read_at IS NULL
                """, user_id, alert_ids)
            else:
                return 0

            return int(result.split()[-1])

    async def send_daily_digest(self):
        """Send daily digest emails to users."""
        async with self.db_pool.acquire() as conn:
            # Find users with pending daily digest alerts
            users = await conn.fetch("""
                SELECT DISTINCT ah.user_id, uac.email_address
                FROM alert_history ah
                JOIN user_alert_configs uac ON ah.user_id = uac.user_id
                WHERE ah.delivery_status = 'pending'
                  AND uac.delivery_frequency = 'daily_digest'
                  AND ah.created_at >= NOW() - INTERVAL '24 hours'
            """)

            for user in users:
                if not self.email_service:
                    continue

                alerts = await conn.fetch("""
                    SELECT * FROM alert_history
                    WHERE user_id = $1
                      AND delivery_status = 'pending'
                      AND created_at >= NOW() - INTERVAL '24 hours'
                    ORDER BY severity DESC, created_at DESC
                """, user['user_id'])

                if alerts:
                    try:
                        await self.email_service.send_digest(
                            email=user['email_address'],
                            alerts=[dict(a) for a in alerts]
                        )

                        # Mark as delivered
                        alert_ids = [a['alert_id'] for a in alerts]
                        await conn.execute("""
                            UPDATE alert_history
                            SET delivered_at = NOW(), delivery_status = 'delivered'
                            WHERE alert_id = ANY($1)
                        """, alert_ids)
                    except Exception as e:
                        logger.error(f"Failed to send digest to {user['user_id']}: {e}")
