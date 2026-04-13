# Alert Database Service - Persistence Layer
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import json

from app.database import get_db_session
from app.models.alert_db import (
    AlertRuleDB,
    AlertDB,
    AlertHistoryDB,
    AlertTypeDB,
    AlertStatusDB,
    AlertSeverityDB,
    NotificationChannelDB,
)
from app.models.alert import (
    AlertRule,
    Alert,
    AlertHistory,
    AlertCreate,
    AlertUpdate,
    AlertType,
    AlertStatus,
    AlertSeverity,
    NotificationChannel,
)

logger = logging.getLogger(__name__)


class AlertDatabaseService:
    """Service for alert database operations"""

    # === Alert Rules ===

    async def get_all_rules(self) -> List[AlertRule]:
        """Get all alert rules from database"""
        async with get_db_session() as session:
            result = await session.execute(select(AlertRuleDB))
            db_rules = result.scalars().all()
            return [self._rule_db_to_model(r) for r in db_rules]

    async def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        """Get a single alert rule by ID"""
        async with get_db_session() as session:
            result = await session.execute(
                select(AlertRuleDB).where(AlertRuleDB.id == rule_id)
            )
            db_rule = result.scalar_one_or_none()
            return self._rule_db_to_model(db_rule) if db_rule else None

    async def create_rule(self, rule: AlertRule) -> AlertRule:
        """Create a new alert rule"""
        async with get_db_session() as session:
            db_rule = self._rule_model_to_db(rule)
            session.add(db_rule)
            await session.flush()
            await session.refresh(db_rule)
            return self._rule_db_to_model(db_rule)

    async def update_rule(self, rule_id: str, update: AlertUpdate) -> Optional[AlertRule]:
        """Update an alert rule"""
        async with get_db_session() as session:
            result = await session.execute(
                select(AlertRuleDB).where(AlertRuleDB.id == rule_id)
            )
            db_rule = result.scalar_one_or_none()
            if not db_rule:
                return None

            if update.name is not None:
                db_rule.name = update.name
            if update.description is not None:
                db_rule.description = update.description
            if update.severity is not None:
                db_rule.severity = AlertSeverityDB(update.severity.value)
            if update.threshold is not None:
                db_rule.threshold = update.threshold
            if update.duration_seconds is not None:
                db_rule.duration_seconds = update.duration_seconds
            if update.channels is not None:
                db_rule.channels = [c.value for c in update.channels]
            if update.recipients is not None:
                db_rule.recipients = update.recipients
            if update.cooldown_seconds is not None:
                db_rule.cooldown_seconds = update.cooldown_seconds
            if update.enabled is not None:
                db_rule.enabled = update.enabled

            db_rule.updated_at = datetime.utcnow()

            await session.flush()
            await session.refresh(db_rule)
            return self._rule_db_to_model(db_rule)

    async def delete_rule(self, rule_id: str) -> bool:
        """Delete an alert rule"""
        async with get_db_session() as session:
            result = await session.execute(
                delete(AlertRuleDB).where(AlertRuleDB.id == rule_id)
            )
            return result.rowcount > 0

    # === Alerts ===

    async def get_all_alerts(
        self,
        status: Optional[AlertStatus] = None,
        alert_type: Optional[AlertType] = None,
        limit: int = 100,
    ) -> List[Alert]:
        """Get alerts with optional filtering"""
        async with get_db_session() as session:
            query = select(AlertDB)

            if status:
                query = query.where(AlertDB.status == AlertStatusDB(status.value))
            if alert_type:
                query = query.where(AlertDB.alert_type == AlertTypeDB(alert_type.value))

            query = query.order_by(AlertDB.triggered_at.desc()).limit(limit)

            result = await session.execute(query)
            db_alerts = result.scalars().all()
            return [self._alert_db_to_model(a) for a in db_alerts]

    async def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get a single alert by ID"""
        async with get_db_session() as session:
            result = await session.execute(
                select(AlertDB).where(AlertDB.id == alert_id)
            )
            db_alert = result.scalar_one_or_none()
            return self._alert_db_to_model(db_alert) if db_alert else None

    async def create_alert(self, alert: Alert) -> Alert:
        """Create a new alert"""
        async with get_db_session() as session:
            db_alert = self._alert_model_to_db(alert)
            session.add(db_alert)
            await session.flush()
            await session.refresh(db_alert)
            return self._alert_db_to_model(db_alert)

    async def update_alert_status(
        self,
        alert_id: str,
        status: AlertStatus,
        acknowledged_by: Optional[str] = None,
    ) -> Optional[Alert]:
        """Update alert status"""
        async with get_db_session() as session:
            result = await session.execute(
                select(AlertDB).where(AlertDB.id == alert_id)
            )
            db_alert = result.scalar_one_or_none()
            if not db_alert:
                return None

            db_alert.status = AlertStatusDB(status.value)

            if status == AlertStatus.ACKNOWLEDGED:
                db_alert.acknowledged_at = datetime.utcnow()
                db_alert.acknowledged_by = acknowledged_by
            elif status == AlertStatus.RESOLVED:
                db_alert.resolved_at = datetime.utcnow()

            await session.flush()
            await session.refresh(db_alert)
            return self._alert_db_to_model(db_alert)

    async def increment_notifications(self, alert_id: str) -> None:
        """Increment notification count for an alert"""
        async with get_db_session() as session:
            result = await session.execute(
                select(AlertDB).where(AlertDB.id == alert_id)
            )
            db_alert = result.scalar_one_or_none()
            if db_alert:
                db_alert.notifications_sent += 1
                db_alert.last_notification_at = datetime.utcnow()

    # === Alert History ===

    async def get_history(
        self,
        alert_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[AlertHistory]:
        """Get alert history"""
        async with get_db_session() as session:
            query = select(AlertHistoryDB)

            if alert_id:
                query = query.where(AlertHistoryDB.alert_id == alert_id)

            query = query.order_by(AlertHistoryDB.timestamp.desc()).limit(limit)

            result = await session.execute(query)
            db_history = result.scalars().all()
            return [self._history_db_to_model(h) for h in db_history]

    async def create_history(self, history: AlertHistory) -> AlertHistory:
        """Create a history entry"""
        async with get_db_session() as session:
            db_history = self._history_model_to_db(history)
            session.add(db_history)
            await session.flush()
            await session.refresh(db_history)
            return self._history_db_to_model(db_history)

    # === Conversion Methods ===

    def _rule_db_to_model(self, db_rule: AlertRuleDB) -> AlertRule:
        """Convert database model to Pydantic model"""
        return AlertRule(
            id=db_rule.id,
            name=db_rule.name,
            description=db_rule.description,
            alert_type=AlertType(db_rule.alert_type.value),
            severity=AlertSeverity(db_rule.severity.value),
            enabled=db_rule.enabled,
            threshold=db_rule.threshold,
            duration_seconds=db_rule.duration_seconds,
            channels=[NotificationChannel(c) for c in db_rule.channels],
            recipients=db_rule.recipients,
            cooldown_seconds=db_rule.cooldown_seconds,
            created_at=db_rule.created_at,
            updated_at=db_rule.updated_at,
            created_by=db_rule.created_by,
        )

    def _rule_model_to_db(self, rule: AlertRule) -> AlertRuleDB:
        """Convert Pydantic model to database model"""
        return AlertRuleDB(
            id=rule.id,
            name=rule.name,
            description=rule.description,
            alert_type=AlertTypeDB(rule.alert_type.value),
            severity=AlertSeverityDB(rule.severity.value),
            enabled=rule.enabled,
            threshold=rule.threshold,
            duration_seconds=rule.duration_seconds,
            channels_json=json.dumps([c.value for c in rule.channels]),
            recipients_json=json.dumps(rule.recipients),
            cooldown_seconds=rule.cooldown_seconds,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
            created_by=rule.created_by,
        )

    def _alert_db_to_model(self, db_alert: AlertDB) -> Alert:
        """Convert database model to Pydantic model"""
        return Alert(
            id=db_alert.id,
            rule_id=db_alert.rule_id,
            rule_name=db_alert.rule_name,
            alert_type=AlertType(db_alert.alert_type.value),
            severity=AlertSeverity(db_alert.severity.value),
            status=AlertStatus(db_alert.status.value),
            title=db_alert.title,
            message=db_alert.message,
            details=db_alert.details,
            device_id=db_alert.device_id,
            task_id=db_alert.task_id,
            triggered_at=db_alert.triggered_at,
            resolved_at=db_alert.resolved_at,
            acknowledged_at=db_alert.acknowledged_at,
            acknowledged_by=db_alert.acknowledged_by,
            notifications_sent=db_alert.notifications_sent,
            last_notification_at=db_alert.last_notification_at,
        )

    def _alert_model_to_db(self, alert: Alert) -> AlertDB:
        """Convert Pydantic model to database model"""
        return AlertDB(
            id=alert.id,
            rule_id=alert.rule_id,
            rule_name=alert.rule_name,
            alert_type=AlertTypeDB(alert.alert_type.value),
            severity=AlertSeverityDB(alert.severity.value),
            status=AlertStatusDB(alert.status.value),
            title=alert.title,
            message=alert.message,
            details_json=json.dumps(alert.details),
            device_id=alert.device_id,
            task_id=alert.task_id,
            triggered_at=alert.triggered_at,
            resolved_at=alert.resolved_at,
            acknowledged_at=alert.acknowledged_at,
            acknowledged_by=alert.acknowledged_by,
            notifications_sent=alert.notifications_sent,
            last_notification_at=alert.last_notification_at,
        )

    def _history_db_to_model(self, db_history: AlertHistoryDB) -> AlertHistory:
        """Convert database model to Pydantic model"""
        return AlertHistory(
            id=db_history.id,
            alert_id=db_history.alert_id,
            action=db_history.action,
            timestamp=db_history.timestamp,
            user_id=db_history.user_id,
            details=db_history.details,
        )

    def _history_model_to_db(self, history: AlertHistory) -> AlertHistoryDB:
        """Convert Pydantic model to database model"""
        return AlertHistoryDB(
            id=history.id,
            alert_id=history.alert_id,
            action=history.action,
            timestamp=history.timestamp,
            user_id=history.user_id,
            details_json=json.dumps(history.details),
        )


# Global instance
alert_db_service = AlertDatabaseService()
