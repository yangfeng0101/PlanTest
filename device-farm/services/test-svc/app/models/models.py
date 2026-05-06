# Data Models for Test Service
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from uuid import uuid4


# Enums
class ScriptType(str, Enum):
    PYTHON = "python"


class ScriptStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DevicePlatform(str, Enum):
    ANDROID = "android"
    IOS = "ios"


# Script Models
class ScriptBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    script_type: ScriptType = ScriptType.PYTHON
    content: str = Field(..., min_length=1)
    tags: List[str] = Field(default_factory=list)


class ScriptCreate(ScriptBase):
    pass


class ScriptUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    script_type: Optional[ScriptType] = None
    content: Optional[str] = Field(None, min_length=1)
    tags: Optional[List[str]] = None
    status: Optional[ScriptStatus] = None


class Script(ScriptBase):
    id: str = Field(default_factory=lambda: str(uuid4()))
    status: ScriptStatus = ScriptStatus.DRAFT
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    file_path: Optional[str] = None

    class Config:
        from_attributes = True


# Task Models
class TaskBase(BaseModel):
    script_id: str
    device_id: Optional[str] = None
    device_platform: DevicePlatform = DevicePlatform.ANDROID
    device_capabilities: Dict[str, Any] = Field(default_factory=dict)
    parameters: Dict[str, Any] = Field(default_factory=dict)


class TaskCreate(TaskBase):
    pass


class Task(TaskBase):
    id: str = Field(default_factory=lambda: str(uuid4()))
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    log_file: Optional[str] = None
    report_id: Optional[str] = None

    class Config:
        from_attributes = True


# Task Log Models
class TaskLogEntry(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    level: str = "INFO"
    message: str
    event_type: Optional[str] = None
    line_number: Optional[int] = None


# Execution Result Models
class ExecutionResult(BaseModel):
    task_id: str
    success: bool
    duration: float  # seconds
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    errors: List[str] = Field(default_factory=list)
    screenshots: List[str] = Field(default_factory=list)
    videos: List[str] = Field(default_factory=list)
    logs: List[TaskLogEntry] = Field(default_factory=list)


# Response Models
class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 1


class ScriptListResponse(PaginatedResponse):
    items: List[Script]


class TaskListResponse(PaginatedResponse):
    items: List[Task]


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None
