# Schedule Models for Test Service
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
from uuid import uuid4
from sqlalchemy import Column, String, Text, DateTime, Boolean, Integer, JSON, Enum as SQLEnum
from app.models.database import Base


class ScheduleType(str, Enum):
    """Type of schedule"""
    CRONTAB = "crontab"      # Cron expression based
    INTERVAL = "interval"    # Interval based (every N seconds/minutes/hours)
    ONETIME = "onetime"      # One-time execution at specific time


class IntervalUnit(str, Enum):
    """Unit for interval scheduling"""
    SECONDS = "seconds"
    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"


class ScheduleStatus(str, Enum):
    """Status of a schedule"""
    ENABLED = "enabled"
    DISABLED = "disabled"
    EXPIRED = "expired"  # For one-time schedules that have executed


# SQLAlchemy Database Model
class ScheduleDB(Base):
    """Schedule database model"""
    __tablename__ = "schedules"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    task = Column(String(255), nullable=False)  # Celery task name
    schedule_type = Column(SQLEnum(ScheduleType), nullable=False)

    # Crontab fields
    minute = Column(String(10), default="*")
    hour = Column(String(10), default="*")
    day_of_month = Column(String(10), default="*")
    month_of_year = Column(String(10), default="*")
    day_of_week = Column(String(10), default="*")

    # Interval fields
    interval_every = Column(Integer, nullable=True)
    interval_unit = Column(SQLEnum(IntervalUnit), nullable=True)

    # One-time fields
    run_at = Column(DateTime, nullable=True)
    executed = Column(Boolean, default=False)

    # Common fields
    args = Column(JSON, default=list)
    kwargs = Column(JSON, default=dict)
    status = Column(SQLEnum(ScheduleStatus), default=ScheduleStatus.ENABLED)
    description = Column(Text, nullable=True)
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    total_run_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Schedule(id={self.id}, name={self.name}, type={self.schedule_type})>"


# Pydantic Models for API
class CrontabConfig(BaseModel):
    """Crontab schedule configuration"""
    minute: str = Field(default="*", description="Cron minute (0-59)")
    hour: str = Field(default="*", description="Cron hour (0-23)")
    day_of_month: str = Field(default="*", description="Cron day of month (1-31)")
    month_of_year: str = Field(default="*", description="Cron month (1-12)")
    day_of_week: str = Field(default="*", description="Cron day of week (0-6, Sunday=0)")


class IntervalConfig(BaseModel):
    """Interval schedule configuration"""
    every: int = Field(..., gt=0, description="Interval value")
    unit: IntervalUnit = Field(default=IntervalUnit.MINUTES, description="Unit for interval")


class OneTimeConfig(BaseModel):
    """One-time schedule configuration"""
    run_at: datetime = Field(..., description="When to run the task")


class ScheduleBase(BaseModel):
    """Base schedule model"""
    name: str = Field(..., min_length=1, max_length=255, description="Unique schedule name")
    task: str = Field(..., min_length=1, description="Celery task name to execute")
    schedule_type: ScheduleType = Field(..., description="Type of schedule")
    args: List[Any] = Field(default_factory=list, description="Positional arguments for task")
    kwargs: Dict[str, Any] = Field(default_factory=dict, description="Keyword arguments for task")
    description: Optional[str] = Field(None, max_length=1000, description="Schedule description")

    @validator('args', pre=True)
    def validate_args(cls, v):
        if v is None:
            return []
        return v

    @validator('kwargs', pre=True)
    def validate_kwargs(cls, v):
        if v is None:
            return {}
        return v


class ScheduleCreate(ScheduleBase):
    """Create schedule request"""
    crontab: Optional[CrontabConfig] = Field(None, description="Crontab config (required if type=CRONTAB)")
    interval: Optional[IntervalConfig] = Field(None, description="Interval config (required if type=INTERVAL)")
    onetime: Optional[OneTimeConfig] = Field(None, description="One-time config (required if type=ONETIME)")
    enabled: bool = Field(default=True, description="Whether schedule is enabled")

    @validator('crontab', always=True)
    def validate_crontab(cls, v, values):
        if values.get('schedule_type') == ScheduleType.CRONTAB and v is None:
            raise ValueError("crontab is required when schedule_type is CRONTAB")
        return v

    @validator('interval', always=True)
    def validate_interval(cls, v, values):
        if values.get('schedule_type') == ScheduleType.INTERVAL and v is None:
            raise ValueError("interval is required when schedule_type is INTERVAL")
        return v

    @validator('onetime', always=True)
    def validate_onetime(cls, v, values):
        if values.get('schedule_type') == ScheduleType.ONETIME and v is None:
            raise ValueError("onetime is required when schedule_type is ONETIME")
        return v


class ScheduleUpdate(BaseModel):
    """Update schedule request"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    task: Optional[str] = Field(None, min_length=1)
    args: Optional[List[Any]] = None
    kwargs: Optional[Dict[str, Any]] = None
    description: Optional[str] = Field(None, max_length=1000)
    crontab: Optional[CrontabConfig] = None
    interval: Optional[IntervalConfig] = None
    onetime: Optional[OneTimeConfig] = None


class Schedule(ScheduleBase):
    """Full schedule model"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    status: ScheduleStatus = Field(default=ScheduleStatus.ENABLED)

    # Crontab fields
    minute: str = "*"
    hour: str = "*"
    day_of_month: str = "*"
    month_of_year: str = "*"
    day_of_week: str = "*"

    # Interval fields
    interval_every: Optional[int] = None
    interval_unit: Optional[IntervalUnit] = None

    # One-time fields
    run_at: Optional[datetime] = None
    executed: bool = False

    # Stats
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    total_run_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True


class ScheduleListResponse(BaseModel):
    """Paginated schedule list response"""
    items: List[Schedule]
    total: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 1


class ScheduleEnableRequest(BaseModel):
    """Request to enable/disable a schedule"""
    enabled: bool = Field(..., description="True to enable, False to disable")


class ScriptRunScheduleMode(str, Enum):
    """Product-level script run schedule modes."""
    ONCE = "once"
    DAILY = "daily"


class ScriptRunScheduleCreate(BaseModel):
    """Create a script run schedule."""
    name: str = Field(..., min_length=1, max_length=255)
    script_id: str = Field(..., min_length=1)
    device_id: str = Field(..., min_length=1)
    schedule_mode: ScriptRunScheduleMode
    run_at: Optional[datetime] = None
    time_of_day: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=100)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    feishu_webhook_url: Optional[str] = Field(None, min_length=1, max_length=1000, exclude=True)
    notification_enabled: bool = False
    enabled: bool = True

    @validator("feishu_webhook_url")
    def validate_feishu_webhook_url(cls, v):
        if v is None:
            return v
        value = v.strip()
        if not value:
            return None
        if not value.startswith("https://"):
            raise ValueError("feishu_webhook_url must start with https://")
        return value

    @validator("notification_enabled")
    def validate_notification_enabled(cls, v, values):
        if v and not values.get("feishu_webhook_url"):
            raise ValueError("feishu_webhook_url is required when notification is enabled")
        return v

    @validator("run_at", always=True)
    def validate_run_at(cls, v, values):
        if values.get("schedule_mode") == ScriptRunScheduleMode.ONCE and v is None:
            raise ValueError("run_at is required when schedule_mode is once")
        return v

    @validator("time_of_day", always=True)
    def validate_time_of_day(cls, v, values):
        if values.get("schedule_mode") == ScriptRunScheduleMode.DAILY and not v:
            raise ValueError("time_of_day is required when schedule_mode is daily")
        return v


class _ScriptRunScheduleBase(BaseModel):
    """Shared fields for script run schedule create/update/response."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    script_id: Optional[str] = Field(None, min_length=1)
    device_id: Optional[str] = Field(None, min_length=1)
    schedule_mode: Optional[ScriptRunScheduleMode] = None
    run_at: Optional[datetime] = None
    time_of_day: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    timezone: Optional[str] = Field(None, min_length=1, max_length=100)
    parameters: Optional[Dict[str, Any]] = None
    notification_enabled: Optional[bool] = None
    feishu_webhook_url: Optional[str] = Field(None, min_length=1, max_length=1000, exclude=True)


class ScriptRunScheduleUpdate(_ScriptRunScheduleBase):
    """Update a script run schedule."""

    @validator("feishu_webhook_url")
    def validate_feishu_webhook_url(cls, v):
        if v is None:
            return v
        value = v.strip()
        if not value:
            return None
        if not value.startswith("https://"):
            raise ValueError("feishu_webhook_url must start with https://")
        return value


class ScriptRunSchedule(BaseModel):
    """Script run schedule response."""
    id: str
    name: str
    script_id: str
    device_id: str
    schedule_mode: ScriptRunScheduleMode
    run_at: Optional[datetime] = None
    time_of_day: Optional[str] = None
    timezone: str = "Asia/Shanghai"
    parameters: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    status: ScheduleStatus
    device_platform: Optional[str] = None
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    total_run_count: int = 0
    executed: bool = False
    last_task_id: Optional[str] = None
    last_task_status: Optional[str] = None
    last_task_error: Optional[str] = None
    last_task_finished_at: Optional[datetime] = None
    last_error: Optional[str] = None
    notification_enabled: bool = False
    feishu_webhook_configured: bool = False
    notification_last_status: Optional[str] = None
    notification_last_error: Optional[str] = None
    notification_last_at: Optional[datetime] = None
    notification_last_task_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ScriptRunScheduleListResponse(BaseModel):
    """Paginated script run schedule list response."""
    items: List[ScriptRunSchedule]
    total: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 1
