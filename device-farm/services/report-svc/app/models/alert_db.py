# Alert Database Models (SQLAlchemy)
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, String, Text, DateTime, Float, Integer, Boolean, Enum as SQLEnum, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base
from enum import Enum
import json


class AlertTypeDB(str, Enum):
    """Alert types"""
    DEVICE_OFFLINE = "device_offline"
    TASK_FAILURE_RATE = "task_failure_rate"
    DEVICE_IDLE = "device_idle"
    CUSTOM = "custom"


class AlertStatusDB(str, Enum):
    """Alert status"""
    ACTIVE = "active"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"


class AlertSeverityDB(str, Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class NotificationChannelDB(str, Enum):
    """Notification channels"""
    FEISHU = "feishu"
    DINGTALK = "dingtalk"
    EMAIL = "email"
    WEBHOOK = "webhook"


class AlertRuleDB(Base):
    """Alert rule database model"""
    __tablename__ = "alert_rules"

    id = Column(String(36), primary_key=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)

    alert_type = Column(
        SQLEnum(AlertTypeDB),
        nullable=False,
        index=True
    )
    severity = Column(
        SQLEnum(AlertSeverityDB),
        default=AlertSeverityDB.WARNING,
        nullable=False
    )
    enabled = Column(Boolean, default=True, nullable=False, index=True)

    # Threshold configuration
    threshold = Column(Float, default=0.0, nullable=False)
    duration_seconds = Column(Integer, default=300, nullable=False)

    # Notification channels stored as JSON array
    channels_json = Column(Text, default="[]", nullable=False)
    recipients_json = Column(Text, default="[]", nullable=False)

    # Cooldown
    cooldown_seconds = Column(Integer, default=300, nullable=False)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(String(100), nullable=True, index=True)

    __table_args__ = (
        Index('ix_alert_rules_type_enabled', 'alert_type', 'enabled'),
    )

    @property
    def channels(self) -> List[str]:
        """Get channels as list"""
        try:
            return json.loads(self.channels_json) if self.channels_json else []
        except json.JSONDecodeError:
            return []

    @channels.setter
    def channels(self, value: List[str]):
        """Set channels from list"""
        self.channels_json = json.dumps(value or [])

    @property
    def recipients(self) -> List[str]:
        """Get recipients as list"""
        try:
            return json.loads(self.recipients_json) if self.recipients_json else []
        except json.JSONDecodeError:
            return []

    @recipients.setter
    def recipients(self, value: List[str]):
        """Set recipients from list"""
        self.recipients_json = json.dumps(value or [])


class AlertDB(Base):
    """Alert instance database model"""
    __tablename__ = "alerts"

    id = Column(String(36), primary_key=True)
    rule_id = Column(String(36), ForeignKey('alert_rules.id'), nullable=False, index=True)
    rule_name = Column(String(200), nullable=False)
    alert_type = Column(
        SQLEnum(AlertTypeDB),
        nullable=False,
        index=True
    )
    severity = Column(
        SQLEnum(AlertSeverityDB),
        nullable=False
    )
    status = Column(
        SQLEnum(AlertStatusDB),
        default=AlertStatusDB.ACTIVE,
        nullable=False,
        index=True
    )

    # Alert details
    title = Column(String(500), nullable=False)
    message = Column(Text, nullable=False)
    details_json = Column(Text, default="{}", nullable=False)

    # Device/Task references
    device_id = Column(String(100), nullable=True, index=True)
    task_id = Column(String(100), nullable=True, index=True)

    # Timestamps
    triggered_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    resolved_at = Column(DateTime, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(String(100), nullable=True, index=True)

    # Notification tracking
    notifications_sent = Column(Integer, default=0, nullable=False)
    last_notification_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index('ix_alerts_status_triggered', 'status', 'triggered_at'),
        Index('ix_alerts_rule_id', 'rule_id'),
    )

    @property
    def details(self) -> dict:
        """Get details as dict"""
        try:
            return json.loads(self.details_json) if self.details_json else {}
        except json.JSONDecodeError:
            return {}

    @details.setter
    def details(self, value: dict):
        """Set details from dict"""
        self.details_json = json.dumps(value or {})


class AlertHistoryDB(Base):
    """Alert history database model"""
    __tablename__ = "alert_history"

    id = Column(String(36), primary_key=True)
    alert_id = Column(String(36), ForeignKey('alerts.id'), nullable=False, index=True)
    action = Column(String(50), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    user_id = Column(String(100), nullable=True, index=True)
    details_json = Column(Text, default="{}", nullable=False)

    __table_args__ = (
        Index('ix_alert_history_alert_timestamp', 'alert_id', 'timestamp'),
    )

    @property
    def details(self) -> dict:
        """Get details as dict"""
        try:
            return json.loads(self.details_json) if self.details_json else {}
        except json.JSONDecodeError:
            return {}

    @details.setter
    def details(self, value: dict):
        """Set details from dict"""
        self.details_json = json.dumps(value or {})
