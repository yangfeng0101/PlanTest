# Alert Models for Device Farm
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel


class AlertType(str, Enum):
    """Alert types"""
    DEVICE_OFFLINE = "device_offline"
    TASK_FAILURE_RATE = "task_failure_rate"
    DEVICE_IDLE = "device_idle"
    CUSTOM = "custom"


class AlertStatus(str, Enum):
    """Alert status"""
    ACTIVE = "active"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class NotificationChannel(str, Enum):
    """Notification channels"""
    FEISHU = "feishu"
    DINGTALK = "dingtalk"
    EMAIL = "email"
    WEBHOOK = "webhook"


class AlertRule(BaseModel):
    """Alert rule configuration"""
    id: str
    name: str
    description: Optional[str] = None
    alert_type: AlertType
    severity: AlertSeverity = AlertSeverity.WARNING
    enabled: bool = True

    # Threshold configuration
    threshold: float = 0.0  # e.g., failure rate threshold
    duration_seconds: int = 300  # How long condition must persist

    # Notification channels
    channels: List[NotificationChannel] = [NotificationChannel.FEISHU]
    recipients: List[str] = []  # Email addresses or webhook URLs

    # Cooldown to prevent spam
    cooldown_seconds: int = 300

    # Metadata
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None


class Alert(BaseModel):
    """Alert instance"""
    id: str
    rule_id: str
    rule_name: str
    alert_type: AlertType
    severity: AlertSeverity
    status: AlertStatus = AlertStatus.ACTIVE

    # Alert details
    title: str
    message: str
    details: Dict[str, Any] = {}

    # Device/Task references
    device_id: Optional[str] = None
    task_id: Optional[str] = None

    # Timestamps
    triggered_at: datetime
    resolved_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None

    # Notification tracking
    notifications_sent: int = 0
    last_notification_at: Optional[datetime] = None


class AlertCreate(BaseModel):
    """Create alert rule request"""
    name: str
    description: Optional[str] = None
    alert_type: AlertType
    severity: AlertSeverity = AlertSeverity.WARNING
    threshold: float = 0.0
    duration_seconds: int = 300
    channels: List[NotificationChannel] = [NotificationChannel.FEISHU]
    recipients: List[str] = []
    cooldown_seconds: int = 300


class AlertUpdate(BaseModel):
    """Update alert rule request"""
    name: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[AlertSeverity] = None
    threshold: Optional[float] = None
    duration_seconds: Optional[int] = None
    channels: Optional[List[NotificationChannel]] = None
    recipients: Optional[List[str]] = None
    cooldown_seconds: Optional[int] = None
    enabled: Optional[bool] = None


class AlertHistory(BaseModel):
    """Alert history entry"""
    id: str
    alert_id: str
    action: str  # triggered, resolved, acknowledged, notification_sent
    timestamp: datetime
    user_id: Optional[str] = None
    details: Dict[str, Any] = {}
