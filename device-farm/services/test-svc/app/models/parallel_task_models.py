# Parallel Task Models - Shared models to avoid circular imports
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field
from uuid import uuid4


class DeviceSelectionStrategy(str, Enum):
    """Strategy for selecting devices"""
    ALL = "all"  # Select all available devices
    RANDOM = "random"  # Randomly select N devices
    SPECIFIC = "specific"  # Use specified device IDs


class ParallelTaskStatus(str, Enum):
    """Status of parallel execution task"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # Some tasks succeeded, some failed


# Configuration
DEFAULT_MAX_CONCURRENCY = 5


class ParallelTaskCreate(BaseModel):
    """Request model for creating a parallel task"""
    script_id: str
    device_ids: Optional[List[str]] = None  # Required for SPECIFIC strategy
    device_platform: Optional[str] = "android"
    selection_strategy: DeviceSelectionStrategy = DeviceSelectionStrategy.ALL
    max_devices: Optional[int] = None  # For RANDOM strategy, how many to select
    max_concurrency: int = Field(default=DEFAULT_MAX_CONCURRENCY, ge=1, le=20)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    device_capabilities: Dict[str, Any] = Field(default_factory=dict)


class SubTaskInfo(BaseModel):
    """Information about a sub-task in parallel execution"""
    task_id: str
    device_id: str
    status: str = "pending"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ParallelTask(BaseModel):
    """Parallel execution task model"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    script_id: str
    status: ParallelTaskStatus = ParallelTaskStatus.PENDING
    selection_strategy: DeviceSelectionStrategy
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    parameters: Dict[str, Any] = Field(default_factory=dict)
    device_capabilities: Dict[str, Any] = Field(default_factory=dict)
    sub_tasks: List[SubTaskInfo] = Field(default_factory=list)
    total_devices: int = 0
    completed_devices: int = 0
    failed_devices: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ParallelTaskSummary(BaseModel):
    """Summary of parallel task execution"""
    parallel_task_id: str
    script_id: str
    status: ParallelTaskStatus
    total_devices: int
    completed_devices: int
    failed_devices: int
    success_rate: float = 0.0
    total_duration: float = 0.0
    sub_tasks: List[SubTaskInfo]
