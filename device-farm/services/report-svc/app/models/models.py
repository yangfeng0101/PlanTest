# Data Models for Report Service
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from uuid import uuid4


# Enums
class ReportStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class ReportFormat(str, Enum):
    HTML = "html"
    PDF = "pdf"
    JSON = "json"
    MARKDOWN = "markdown"


# Report Models
class ReportBase(BaseModel):
    task_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class ReportCreate(ReportBase):
    pass


class TestSummary(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration: float = 0.0  # seconds
    success_rate: float = 0.0  # percentage


class TestCaseResult(BaseModel):
    name: str
    status: str  # passed, failed, skipped
    duration: float = 0.0
    message: Optional[str] = None
    error: Optional[str] = None
    screenshots: List[str] = Field(default_factory=list)


class ReportDetail(BaseModel):
    summary: TestSummary = Field(default_factory=TestSummary)
    test_cases: List[TestCaseResult] = Field(default_factory=list)
    environment: Dict[str, Any] = Field(default_factory=dict)
    execution_log: List[str] = Field(default_factory=list)
    artifacts: List[str] = Field(default_factory=list)


class Report(ReportBase):
    id: str = Field(default_factory=lambda: str(uuid4()))
    status: ReportStatus = ReportStatus.PENDING
    format: ReportFormat = ReportFormat.HTML
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    detail: Optional[ReportDetail] = None

    class Config:
        from_attributes = True


# Response Models
class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 1


class ReportListResponse(PaginatedResponse):
    items: List[Report]


class ReportDownloadResponse(BaseModel):
    file_name: str
    content_type: str
    file_size: int
    download_url: Optional[str] = None


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None
