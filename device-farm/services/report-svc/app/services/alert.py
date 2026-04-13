# Alert Service for Device Farm
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from collections import defaultdict
import uuid
import logging
import asyncio

from app.models.alert import (
    AlertRule,
    Alert,
    AlertCreate,
    AlertUpdate,
    AlertHistory,
    AlertType,
    AlertStatus,
    AlertSeverity,
    NotificationChannel,
)
from app.services.alert_db_service import alert_db_service
from app.services.notification import (
    notification_service,
    NotificationMessage,
    NotificationChannel as NotifyChannel,
)

logger = logging.getLogger(__name__)


class AlertService:
    """Service for managing alerts and notifications with database persistence"""

    def __init__(self):
        # In-memory cache for performance
        self._rules_cache: Dict[str, AlertRule] = {}
        self._alerts_cache: Dict[str, Alert] = {}
        self._initialized = False

    async def initialize(self):
        """Load data from database into memory cache"""
        if self._initialized:
            return

        try:
            # Load rules from database
            rules = await alert_db_service.get_all_rules()
            for rule in rules:
                self._rules_cache[rule.id] = rule

            # Load active alerts from database
            alerts = await alert_db_service.get_all_alerts(limit=1000)
            for alert in alerts:
                self._alerts_cache[alert.id] = alert

            self._initialized = True
            logger.info(f"Loaded {len(rules)} rules and {len(alerts)} alerts from database")
        except Exception as e:
            logger.error(f"Error loading from database: {e}")

    def create_rule(
        self,
        rule: AlertCreate,
        user_id: Optional[str] = None,
    ) -> AlertRule:
        """Create a new alert rule"""
        now = datetime.utcnow()
        rule_id = str(uuid.uuid4())

        new_rule = AlertRule(
            id=rule_id,
            name=rule.name,
            description=rule.description,
            alert_type=rule.alert_type,
            severity=rule.severity,
            threshold=rule.threshold,
            duration_seconds=rule.duration_seconds,
            channels=rule.channels,
            recipients=rule.recipients,
            cooldown_seconds=rule.cooldown_seconds,
            created_at=now,
            updated_at=now,
            created_by=user_id,
        )

        # Update cache
        self._rules_cache[rule_id] = new_rule

        # Persist to database
        asyncio.create_task(self._persist_rule(new_rule))

        logger.info(f"Created alert rule: {rule_id} - {rule.name}")
        return new_rule

    async def _persist_rule(self, rule: AlertRule):
        """Persist rule to database"""
        try:
            await alert_db_service.create_rule(rule)
        except Exception as e:
            logger.error(f"Error persisting rule {rule.id}: {e}")

    def update_rule(
        self,
        rule_id: str,
        update: AlertUpdate,
    ) -> Optional[AlertRule]:
        """Update an alert rule"""
        rule = self._rules_cache.get(rule_id)
        if not rule:
            return None

        # Update fields
        if update.name is not None:
            rule.name = update.name
        if update.description is not None:
            rule.description = update.description
        if update.severity is not None:
            rule.severity = update.severity
        if update.threshold is not None:
            rule.threshold = update.threshold
        if update.duration_seconds is not None:
            rule.duration_seconds = update.duration_seconds
        if update.channels is not None:
            rule.channels = update.channels
        if update.recipients is not None:
            rule.recipients = update.recipients
        if update.cooldown_seconds is not None:
            rule.cooldown_seconds = update.cooldown_seconds
        if update.enabled is not None:
            rule.enabled = update.enabled

        rule.updated_at = datetime.utcnow()

        # Persist to database
        asyncio.create_task(alert_db_service.update_rule(rule_id, update))

        logger.info(f"Updated alert rule: {rule_id}")
        return rule

    def delete_rule(self, rule_id: str) -> bool:
        """Delete an alert rule"""
        if rule_id in self._rules_cache:
            del self._rules_cache[rule_id]

            # Persist to database
            asyncio.create_task(alert_db_service.delete_rule(rule_id))

            logger.info(f"Deleted alert rule: {rule_id}")
            return True
        return False

    def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        """Get a specific alert rule"""
        return self._rules_cache.get(rule_id)

    def list_rules(
        self,
        enabled_only: bool = False,
    ) -> List[AlertRule]:
        """List all alert rules"""
        rules = list(self._rules_cache.values())
        if enabled_only:
            rules = [r for r in rules if r.enabled]
        return rules

    async def trigger_alert(
        self,
        rule_id: str,
        title: str,
        message: str,
        details: Dict[str, Any] = None,
        device_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Optional[Alert]:
        """Trigger an alert"""
        rule = self._rules_cache.get(rule_id)
        if not rule or not rule.enabled:
            return None

        # Check cooldown
        existing_alerts = [
            a for a in self._alerts_cache.values()
            if a.rule_id == rule_id and a.status == AlertStatus.ACTIVE
        ]
        if existing_alerts:
            last_alert = max(existing_alerts, key=lambda a: a.triggered_at)
            if datetime.utcnow() - last_alert.triggered_at < timedelta(seconds=rule.cooldown_seconds):
                logger.debug(f"Alert in cooldown: {rule_id}")
                return None

        # Create alert
        alert_id = str(uuid.uuid4())
        alert = Alert(
            id=alert_id,
            rule_id=rule_id,
            rule_name=rule.name,
            alert_type=rule.alert_type,
            severity=rule.severity,
            title=title,
            message=message,
            details=details or {},
            device_id=device_id,
            task_id=task_id,
            triggered_at=datetime.utcnow(),
        )

        # Update cache
        self._alerts_cache[alert_id] = alert

        # Persist to database
        await alert_db_service.create_alert(alert)

        # Record history
        await self._record_history(
            alert_id=alert_id,
            action="triggered",
            details={"title": title, "message": message},
        )

        # Send notifications
        await self._send_notifications(alert, rule)

        logger.info(f"Triggered alert: {alert_id} - {title}")
        return alert

    def resolve_alert(
        self,
        alert_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[Alert]:
        """Resolve an alert"""
        alert = self._alerts_cache.get(alert_id)
        if not alert:
            return None

        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.utcnow()

        # Persist to database
        asyncio.create_task(alert_db_service.update_alert_status(
            alert_id, AlertStatus.RESOLVED
        ))

        # Record history
        asyncio.create_task(self._record_history(
            alert_id=alert_id,
            action="resolved",
            user_id=user_id,
        ))

        logger.info(f"Resolved alert: {alert_id}")
        return alert

    def acknowledge_alert(
        self,
        alert_id: str,
        user_id: str,
    ) -> Optional[Alert]:
        """Acknowledge an alert"""
        alert = self._alerts_cache.get(alert_id)
        if not alert:
            return None

        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.utcnow()
        alert.acknowledged_by = user_id

        # Persist to database
        asyncio.create_task(alert_db_service.update_alert_status(
            alert_id, AlertStatus.ACKNOWLEDGED, user_id
        ))

        # Record history
        asyncio.create_task(self._record_history(
            alert_id=alert_id,
            action="acknowledged",
            user_id=user_id,
        ))

        logger.info(f"Acknowledged alert: {alert_id} by {user_id}")
        return alert

    def list_alerts(
        self,
        status: Optional[AlertStatus] = None,
        alert_type: Optional[AlertType] = None,
        limit: int = 100,
    ) -> List[Alert]:
        """List alerts with optional filtering"""
        alerts = list(self._alerts_cache.values())

        if status:
            alerts = [a for a in alerts if a.status == status]
        if alert_type:
            alerts = [a for a in alerts if a.alert_type == alert_type]

        # Sort by triggered_at descending
        alerts.sort(key=lambda a: a.triggered_at, reverse=True)
        return alerts[:limit]

    async def get_history(
        self,
        alert_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[AlertHistory]:
        """Get alert history"""
        return await alert_db_service.get_history(alert_id=alert_id, limit=limit)

    async def send_feishu_notification(
        self,
        webhook_url: str,
        alert: Alert,
    ) -> bool:
        """Send notification to Feishu"""
        message = NotificationMessage(
            title=alert.title,
            content=alert.message,
            severity=alert.severity.value,
            details={
                "类型": alert.alert_type.value,
                "时间": alert.triggered_at.isoformat(),
                **alert.details,
            },
        )

        # Create a temporary service with the specific webhook
        from app.services.notification import NotificationService
        service = NotificationService(feishu_webhook=webhook_url)
        return await service.send_feishu(message)

    async def send_dingtalk_notification(
        self,
        webhook_url: str,
        alert: Alert,
    ) -> bool:
        """Send notification to DingTalk"""
        message = NotificationMessage(
            title=alert.title,
            content=alert.message,
            severity=alert.severity.value,
            details={
                "类型": alert.alert_type.value,
                "时间": alert.triggered_at.isoformat(),
                **alert.details,
            },
        )

        # Create a temporary service with the specific webhook
        from app.services.notification import NotificationService
        service = NotificationService(dingtalk_webhook=webhook_url)
        return await service.send_dingtalk(message)

    async def send_email_notification(
        self,
        email: str,
        alert: Alert,
    ) -> bool:
        """Send email notification"""
        message = NotificationMessage(
            title=alert.title,
            content=alert.message,
            severity=alert.severity.value,
            details={
                "类型": alert.alert_type.value,
                "时间": alert.triggered_at.isoformat(),
                **alert.details,
            },
        )

        return await notification_service.send_email(message, [email])

    async def _send_notifications(
        self,
        alert: Alert,
        rule: AlertRule,
    ) -> None:
        """Send notifications through configured channels"""
        notification_tasks = []

        for channel in rule.channels:
            for recipient in rule.recipients:
                if channel == NotificationChannel.FEISHU:
                    notification_tasks.append(
                        self.send_feishu_notification(recipient, alert)
                    )
                elif channel == NotificationChannel.DINGTALK:
                    notification_tasks.append(
                        self.send_dingtalk_notification(recipient, alert)
                    )
                elif channel == NotificationChannel.EMAIL:
                    notification_tasks.append(
                        self.send_email_notification(recipient, alert)
                    )

        # Execute all notifications in parallel
        if notification_tasks:
            results = await asyncio.gather(*notification_tasks, return_exceptions=True)

            # Log results
            success_count = sum(1 for r in results if r is True)
            logger.info(
                f"Sent {success_count}/{len(notification_tasks)} notifications for alert {alert.id}"
            )

        alert.notifications_sent += 1
        alert.last_notification_at = datetime.utcnow()

        # Update notification count in database
        await alert_db_service.increment_notifications(alert.id)

        await self._record_history(
            alert_id=alert.id,
            action="notification_sent",
            details={"channels": [c.value for c in rule.channels]},
        )

    async def _record_history(
        self,
        alert_id: str,
        action: str,
        user_id: Optional[str] = None,
        details: Dict[str, Any] = None,
    ) -> None:
        """Record alert history"""
        history = AlertHistory(
            id=str(uuid.uuid4()),
            alert_id=alert_id,
            action=action,
            timestamp=datetime.utcnow(),
            user_id=user_id,
            details=details or {},
        )

        await alert_db_service.create_history(history)


# Global instance
alert_service = AlertService()
