# Alert Service for Device Farm
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from collections import defaultdict
import uuid
import logging
import httpx

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

logger = logging.getLogger(__name__)

# In-memory storage (in production, use database)
_alert_rules: Dict[str, AlertRule] = {}
_active_alerts: Dict[str, Alert] = {}
_alert_history: List[AlertHistory] = []


class AlertService:
    """Service for managing alerts and notifications"""

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

        _alert_rules[rule_id] = new_rule
        logger.info(f"Created alert rule: {rule_id} - {rule.name}")
        return new_rule

    def update_rule(
        self,
        rule_id: str,
        update: AlertUpdate,
    ) -> Optional[AlertRule]:
        """Update an alert rule"""
        rule = _alert_rules.get(rule_id)
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
        logger.info(f"Updated alert rule: {rule_id}")
        return rule

    def delete_rule(self, rule_id: str) -> bool:
        """Delete an alert rule"""
        if rule_id in _alert_rules:
            del _alert_rules[rule_id]
            logger.info(f"Deleted alert rule: {rule_id}")
            return True
        return False

    def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        """Get a specific alert rule"""
        return _alert_rules.get(rule_id)

    def list_rules(
        self,
        enabled_only: bool = False,
    ) -> List[AlertRule]:
        """List all alert rules"""
        rules = list(_alert_rules.values())
        if enabled_only:
            rules = [r for r in rules if r.enabled]
        return rules

    def trigger_alert(
        self,
        rule_id: str,
        title: str,
        message: str,
        details: Dict[str, Any] = None,
        device_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Optional[Alert]:
        """Trigger an alert"""
        rule = _alert_rules.get(rule_id)
        if not rule or not rule.enabled:
            return None

        # Check cooldown
        existing_alerts = [
            a for a in _active_alerts.values()
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

        _active_alerts[alert_id] = alert

        # Record history
        self._record_history(
            alert_id=alert_id,
            action="triggered",
            details={"title": title, "message": message},
        )

        # Send notifications
        self._send_notifications(alert, rule)

        logger.info(f"Triggered alert: {alert_id} - {title}")
        return alert

    def resolve_alert(
        self,
        alert_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[Alert]:
        """Resolve an alert"""
        alert = _active_alerts.get(alert_id)
        if not alert:
            return None

        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.utcnow()

        # Record history
        self._record_history(
            alert_id=alert_id,
            action="resolved",
            user_id=user_id,
        )

        logger.info(f"Resolved alert: {alert_id}")
        return alert

    def acknowledge_alert(
        self,
        alert_id: str,
        user_id: str,
    ) -> Optional[Alert]:
        """Acknowledge an alert"""
        alert = _active_alerts.get(alert_id)
        if not alert:
            return None

        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.utcnow()
        alert.acknowledged_by = user_id

        # Record history
        self._record_history(
            alert_id=alert_id,
            action="acknowledged",
            user_id=user_id,
        )

        logger.info(f"Acknowledged alert: {alert_id} by {user_id}")
        return alert

    def list_alerts(
        self,
        status: Optional[AlertStatus] = None,
        alert_type: Optional[AlertType] = None,
        limit: int = 100,
    ) -> List[Alert]:
        """List alerts with optional filtering"""
        alerts = list(_active_alerts.values())

        if status:
            alerts = [a for a in alerts if a.status == status]
        if alert_type:
            alerts = [a for a in alerts if a.alert_type == alert_type]

        # Sort by triggered_at descending
        alerts.sort(key=lambda a: a.triggered_at, reverse=True)
        return alerts[:limit]

    def get_history(
        self,
        alert_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[AlertHistory]:
        """Get alert history"""
        history = _alert_history

        if alert_id:
            history = [h for h in history if h.alert_id == alert_id]

        # Sort by timestamp descending
        history.sort(key=lambda h: h.timestamp, reverse=True)
        return history[:limit]

    async def send_feishu_notification(
        self,
        webhook_url: str,
        alert: Alert,
    ) -> bool:
        """Send notification to Feishu"""
        try:
            # Feishu card message format
            card = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {
                            "tag": "plain_text",
                            "content": f"[{alert.severity.value.upper()}] {alert.title}"
                        },
                        "template": self._get_feishu_color(alert.severity)
                    },
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "plain_text",
                                "content": alert.message
                            }
                        },
                        {
                            "tag": "div",
                            "fields": [
                                {
                                    "is_short": True,
                                    "text": {
                                        "tag": "lark_md",
                                        "content": f"**类型**: {alert.alert_type.value}"
                                    }
                                },
                                {
                                    "is_short": True,
                                    "text": {
                                        "tag": "lark_md",
                                        "content": f"**时间**: {alert.triggered_at.isoformat()}"
                                    }
                                }
                            ]
                        }
                    ]
                }
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(webhook_url, json=card, timeout=10)
                return response.status_code == 200

        except Exception as e:
            logger.error(f"Failed to send Feishu notification: {e}")
            return False

    async def send_dingtalk_notification(
        self,
        webhook_url: str,
        alert: Alert,
    ) -> bool:
        """Send notification to DingTalk"""
        try:
            message = {
                "msgtype": "markdown",
                "markdown": {
                    "title": f"[{alert.severity.value.upper()}] {alert.title}",
                    "text": f"### {alert.title}\n\n"
                            f"**严重程度**: {alert.severity.value}\n\n"
                            f"**类型**: {alert.alert_type.value}\n\n"
                            f"**详情**: {alert.message}\n\n"
                            f"**时间**: {alert.triggered_at.isoformat()}"
                }
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(webhook_url, json=message, timeout=10)
                return response.status_code == 200

        except Exception as e:
            logger.error(f"Failed to send DingTalk notification: {e}")
            return False

    async def send_email_notification(
        self,
        email: str,
        alert: Alert,
    ) -> bool:
        """Send email notification (placeholder - requires SMTP config)"""
        # In production, integrate with email service
        logger.info(f"Email notification to {email}: {alert.title}")
        return True

    def _send_notifications(
        self,
        alert: Alert,
        rule: AlertRule,
    ) -> None:
        """Send notifications through configured channels"""
        for channel in rule.channels:
            for recipient in rule.recipients:
                if channel == NotificationChannel.FEISHU:
                    # Send async (fire and forget in this context)
                    import asyncio
                    asyncio.create_task(
                        self.send_feishu_notification(recipient, alert)
                    )
                elif channel == NotificationChannel.DINGTALK:
                    import asyncio
                    asyncio.create_task(
                        self.send_dingtalk_notification(recipient, alert)
                    )
                elif channel == NotificationChannel.EMAIL:
                    import asyncio
                    asyncio.create_task(
                        self.send_email_notification(recipient, alert)
                    )

        alert.notifications_sent += 1
        alert.last_notification_at = datetime.utcnow()

        self._record_history(
            alert_id=alert.id,
            action="notification_sent",
            details={"channels": [c.value for c in rule.channels]},
        )

    def _record_history(
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
        _alert_history.append(history)

    def _get_feishu_color(self, severity: AlertSeverity) -> str:
        """Get Feishu card color for severity"""
        colors = {
            AlertSeverity.INFO: "blue",
            AlertSeverity.WARNING: "yellow",
            AlertSeverity.ERROR: "red",
            AlertSeverity.CRITICAL: "red",
        }
        return colors.get(severity, "blue")


# Global instance
alert_service = AlertService()
